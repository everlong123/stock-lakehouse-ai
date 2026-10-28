"""Unit tests for same-bar duplicate detection.

Covers the failure modes found in the real lakehouse:
  * Two providers stamping the SAME session at different hours
    (yfinance_eod 04:00Z vs yahoo_http 13:30Z) -> one row survives.
  * Genuine intraday ticks on the same day (AAPL 2026-10-13: 13 rows at
    2-second spacing with different prices) -> ALL rows survive. This is the
    case that a naive "collapse by calendar day" fix would destroy.
  * The canonical row that survives is the one matching the symbol's
    dominant session stamp, so the usual EOD bar is the one kept.
  * Bars on different days are never merged.
  * Rows with genuinely different prices on the same day are never merged.
  * Provider float rounding within tolerance still matches.
  * A genuine one-cent move on the same day does NOT match.
  * Bronze.append no longer writes the re-stamped duplicate to storage.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.dedupe import dedupe_same_bars, find_same_bar_duplicates
from app.lakehouse.local_storage import LocalStorageBackend
from app.lakehouse.silver import SilverLayer


def _row(
    symbol: str = "AAPL",
    ts: str = "2026-10-09 13:30:00",
    close: float = 100.0,
    source: str = "yahoo_http",
    open_: float = 99.0,
    high: float = 101.0,
    low: float = 98.0,
    volume: float = 1_000_000.0,
    ingested: str = "2026-10-10 00:00:00",
) -> dict:
    return {
        "symbol": symbol,
        "timestamp": pd.Timestamp(ts, tz="UTC"),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "adj_close": close,
        "volume": volume,
        "source": source,
        "ingestion_time": pd.Timestamp(ingested, tz="UTC"),
    }


# ── The core case: same session, two stamps ───────────────────────────────


def test_same_session_two_stamps_collapses_to_one() -> None:
    """yfinance_eod 04:00Z and yahoo_http 13:30Z describe the same NYSE bar."""
    frame = pd.DataFrame(
        [
            _row(ts="2026-10-09 04:00:00", source="yfinance_eod", ingested="2026-10-14 11:41:00"),
            _row(ts="2026-10-09 13:30:00", source="yahoo_http", ingested="2026-10-19 07:14:00"),
        ]
    )

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 1
    assert len(cleaned) == 1
    # The 13:30 stamp is the symbol's dominant convention, so it must survive.
    assert cleaned.iloc[0]["timestamp"] == pd.Timestamp("2026-10-09 13:30:00", tz="UTC")
    assert cleaned.iloc[0]["source"] == "yahoo_http"


def test_survivor_is_the_modal_stamp_even_when_it_arrives_second() -> None:
    """Ordering must not decide the winner; the symbol's convention must."""
    frame = pd.DataFrame(
        [
            _row(ts="2026-10-09 13:30:00", source="yahoo_http", ingested="2026-10-19 07:14:00"),
            _row(ts="2026-10-09 04:00:00", source="yfinance_eod", ingested="2026-10-14 11:41:00"),
        ]
    )

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 1
    assert len(cleaned) == 1
    assert cleaned.iloc[0]["timestamp"] == pd.Timestamp("2026-10-09 13:30:00", tz="UTC")


def test_symbol_stamped_at_20_keeps_its_own_convention() -> None:
    """A symbol whose bars are stamped 20:00Z must not be forced onto 13:30Z."""
    rows = [_row(symbol="QQQ", ts=f"2026-10-{d:02d} 20:00:00", close=100 + d) for d in (1, 2, 3)]
    rows.append(_row(symbol="QQQ", ts="2026-10-03 13:30:00", close=103, ingested="2026-10-10 00:00:00"))
    frame = pd.DataFrame(rows)

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 1
    assert len(cleaned) == 3
    surviving = cleaned[cleaned["timestamp"].dt.day == 3]
    assert len(surviving) == 1
    assert surviving.iloc[0]["timestamp"] == pd.Timestamp("2026-10-03 20:00:00", tz="UTC")


# ── The case a day-dedupe would destroy ──────────────────────────────────


def test_same_price_ticks_2_seconds_apart_are_all_preserved() -> None:
    """AAPL 2026-10-13 18:52:00..18:52:22: six ticks, identical close.

    This is the case a pure price comparison gets wrong. The market was flat,
    so all six ticks carry close=333.90. They are six real observations two
    seconds apart, and collapsing them would silently delete five ticks. A
    re-stamped session is hours away, never seconds, so the time gap is what
    separates the two populations.
    """
    base = pd.Timestamp("2026-10-13 18:52:00", tz="UTC")
    rows = [
        _row(
            ts=(base + pd.Timedelta(seconds=2 * i)).strftime("%Y-%m-%d %H:%M:%S"),
            close=333.90,
            open_=333.70,
            high=334.20,
            low=333.10,
            volume=18_900.0,
            source="manual",
        )
        for i in range(6)
    ]
    frame = pd.DataFrame(rows)

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 0
    assert len(cleaned) == 6


def test_intraday_ticks_are_all_preserved() -> None:
    """AAPL 2026-10-13: 13 real ticks at 2-second spacing must all survive."""
    rows = []
    for i in range(13):
        rows.append(
            _row(
                ts="2026-10-13 18:44:14",
                close=333.55 + i * 0.1,
                open_=333.50 + i * 0.1,
                high=333.60 + i * 0.1,
                low=333.40 + i * 0.1,
                volume=18_000.0 + i * 100,
                source="manual",
            )
        )
    frame = pd.DataFrame(rows)

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 0
    assert len(cleaned) == 13


def test_same_day_different_prices_are_never_merged() -> None:
    """Two bars on one day that moved are two real bars."""
    frame = pd.DataFrame(
        [
            _row(ts="2026-10-09 13:30:00", close=100.0),
            _row(ts="2026-10-09 14:30:00", close=101.5, open_=100.5, high=102.0, low=100.2),
        ]
    )

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 0
    assert len(cleaned) == 2


def test_one_cent_move_is_not_a_duplicate() -> None:
    """A real one-cent move must not be swallowed by a loose tolerance."""
    frame = pd.DataFrame(
        [
            _row(ts="2026-10-09 13:30:00", close=100.0),
            _row(ts="2026-10-09 20:00:00", close=100.01, open_=99.0, high=101.0, low=98.0),
        ]
    )

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 0
    assert len(cleaned) == 2


def test_different_days_are_never_merged() -> None:
    """Identical prices on different days are different bars."""
    frame = pd.DataFrame(
        [
            _row(ts="2026-10-09 13:30:00", close=100.0),
            _row(ts="2026-10-12 13:30:00", close=100.0),
        ]
    )

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 0
    assert len(cleaned) == 2


def test_different_symbols_are_never_merged() -> None:
    """Same day, same price, different symbol - two legitimate bars."""
    frame = pd.DataFrame(
        [
            _row(symbol="AAPL", ts="2026-10-09 13:30:00", close=100.0),
            _row(symbol="MSFT", ts="2026-10-09 13:30:00", close=100.0),
        ]
    )

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 0
    assert len(cleaned) == 2


def test_provider_float_rounding_still_matches() -> None:
    """Two providers round differently; the bar is still the same bar."""
    frame = pd.DataFrame(
        [
            _row(ts="2026-10-09 13:30:00", close=336.6400146484375, open_=331.70001220703125, high=338.6099853515625, low=330.70001220703125),
            _row(ts="2026-10-09 20:00:00", close=336.640015, open_=331.700012, high=338.609985, low=330.700012),
        ]
    )

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 1
    assert len(cleaned) == 1


# ── Edge cases ────────────────────────────────────────────────────────────


def test_empty_frame_is_handled() -> None:
    empty = pd.DataFrame()
    cleaned, removed = dedupe_same_bars(empty)
    assert removed == 0
    assert cleaned.empty


def test_no_duplicates_leaves_frame_untouched() -> None:
    frame = pd.DataFrame([_row(ts=f"2026-10-{d:02d} 13:30:00", close=100 + d) for d in (1, 2, 3)])

    cleaned, removed = dedupe_same_bars(frame)

    assert removed == 0
    assert len(cleaned) == 3
    assert list(cleaned.index) == list(frame.index)


def test_find_same_bar_duplicates_returns_droppable_subset() -> None:
    frame = pd.DataFrame(
        [
            _row(ts="2026-10-09 13:30:00", close=100.0),
            _row(ts="2026-10-09 04:00:00", close=100.0),
        ]
    )

    dups = find_same_bar_duplicates(frame)

    assert len(dups) == 1
    assert dups.iloc[0]["timestamp"] == pd.Timestamp("2026-10-09 04:00:00", tz="UTC")


# ── Integration with the layers ──────────────────────────────────────────


@pytest.fixture
def tmp_storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(root=tmp_path)


def test_bronze_append_does_not_store_the_restamped_duplicate(tmp_storage: LocalStorageBackend) -> None:
    """The re-stamped session must not reach storage a second time."""
    bronze = BronzeLayer(storage=tmp_storage)

    first = pd.DataFrame([_row(ts="2026-10-09 13:30:00", source="yahoo_http")])
    bronze.append(first)

    second = pd.DataFrame([_row(ts="2026-10-09 04:00:00", source="yfinance_eod")])
    bronze.append(second)

    stored = bronze.read("AAPL")
    assert len(stored) == 1
    assert stored.iloc[0]["timestamp"] == pd.Timestamp("2026-10-09 13:30:00", tz="UTC")


def test_silver_collapses_the_restamped_duplicate(tmp_storage: LocalStorageBackend) -> None:
    """Silver must report the collapse in its quality report.

    The two rows carry DIFFERENT timestamps (13:30 and 04:00) but identical
    prices, so they survive the exact-timestamp pass and are removed by the
    price based one.
    """
    silver = SilverLayer(storage=tmp_storage)

    frame = pd.DataFrame(
        [
            _row(ts="2026-10-09 13:30:00", source="yahoo_http"),
            _row(ts="2026-10-09 04:00:00", source="yfinance_eod"),
        ]
    )

    valid, quality = silver.transform(frame)

    assert len(valid) == 1
    assert quality["same_bar_count"] == 1
    assert quality["record_count"] == 1


def test_silver_collapses_intraday_ticks_into_one_daily_bar(tmp_storage: LocalStorageBackend) -> None:
    """Silver must collapse real intraday ticks into ONE daily bar.

    The fixture mirrors AAPL 2026-10-13 as actually stored: 13 ticks at
    2-second spacing, each with its own timestamp and a moving price.

    WHY the ticks must be collapsed: the lakehouse is single-interval
    (daily only), so those 13 rows are not 13 observations of interest -
    they are one trading session that happened to be recorded tick by
    tick. Keeping them meant the daily chart drew 13 candles for
    2026-10-13, the day's "close" was whatever the last tick happened to
    be (333.9 against the real session close of 341.27, which reads as a
    ~2% crash that never happened), and every rolling window counted the
    session 13 times - which shifts SMA/RSI/MACD and outright breaks the
    argmax-based indicators (Aroon, Stochastic, Williams %R, CCI).

    The ticks are AGGREGATED, not discarded: open = first, high = max,
    low = min, close = last, volume = sum.
    """
    silver = SilverLayer(storage=tmp_storage)

    base = pd.Timestamp("2026-10-13 18:44:14", tz="UTC")
    rows = [
        _row(
            ts=(base + pd.Timedelta(seconds=2 * i)).strftime("%Y-%m-%d %H:%M:%S"),
            close=333.55 + i * 0.1,
            open_=333.50 + i * 0.1,
            high=333.60 + i * 0.1,
            low=333.40 + i * 0.1,
            volume=18_000.0 + i * 100,
            source="manual",
        )
        for i in range(13)
    ]

    valid, quality = silver.transform(pd.DataFrame(rows))

    assert len(valid) == 1, "one trading day must yield exactly one daily bar"
    assert quality["same_bar_count"] == 0
    assert quality["intraday_days_aggregated"] == 1
    assert quality["intraday_rows_aggregated"] == 13

    bar = valid.iloc[0]
    assert bar["open"] == 333.50      # first tick
    assert bar["close"] == 334.75     # last tick
    assert bar["high"] == 334.80      # max
    assert bar["low"] == 333.40       # min
    assert bar["volume"] == sum(18_000.0 + i * 100 for i in range(13))


def test_silver_drops_same_timestamp_rows_by_its_existing_rule(tmp_storage: LocalStorageBackend) -> None:
    """Document the pre-existing behaviour that same-timestamp rows collapse.

    Silver has always deduplicated on (symbol, timestamp). This is correct for
    a tick feed and is what the fixture above avoids by giving each tick its
    own timestamp. The assertion is here so the distinction between the two
    dedupe rules stays explicit rather than implicit in a fixture.
    """
    silver = SilverLayer(storage=tmp_storage)

    frame = pd.DataFrame(
        [
            _row(ts="2026-10-13 18:44:14", close=333.55, open_=333.50, high=333.60, low=333.40, source="manual"),
            _row(ts="2026-10-13 18:44:14", close=333.65, open_=333.60, high=333.70, low=333.50, source="manual"),
        ]
    )

    valid, quality = silver.transform(frame)

    assert len(valid) == 1
    # Same timestamp, so this is handled by the pre-existing exact-timestamp
    # rule and reported as a duplicate, not as a re-stamped session.
    assert quality["duplicate_count"] == 1
    assert quality["same_bar_count"] == 0
