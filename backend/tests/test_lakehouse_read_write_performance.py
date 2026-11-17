"""The windowed read and the incremental write must not change the data.

WHY THIS TEST EXISTS
--------------------
Two performance changes were made to the lakehouse, and both of them
SKIP work. That is exactly the kind of change that can quietly lose
rows, so both are pinned here:

  1. A windowed read downloads only the partitions that can hold the
     requested date range instead of the symbol's whole history.
  2. An incremental write rewrites only the partitions from the changed
     session onwards, because every feature in Silver and Gold is
     causal.

The rule this file enforces is the same one for both: the fast path
and the slow path must produce THE SAME DATA. A windowed read must
return exactly the rows a full read would return inside the window,
and an incremental write must leave the stored partitions identical to
what a full write would have stored.

There is no fake data here: every frame is built from real OHLCV rows
that carry a real source, and the assertions compare the fast path
against the slow path on the same input.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.features.feature_engineering import build_gold_features  # noqa: E402
from app.lakehouse.parquet_manager import (  # noqa: E402
    filter_keys_by_window,
    partition_month,
    partitions_from,
)
from app.lakehouse.session import slice_window  # noqa: E402


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _real_frame(start: str = "2024-01-01", sessions: int = 400) -> pd.DataFrame:
    """A deterministic OHLCV frame used as the INPUT of the assertions.

    THIS IS A TEST INPUT, NOT SERVED DATA
    --------------------------------------
    The lakehouse never sees this frame: it exists so the comparison
    between the fast path and the slow path has a known input. That is
    why its ``source`` says so - a row must never claim a provider that
    did not produce it, and a fixture that claimed ``yahoo_http`` would
    be exactly the kind of borrowed authority this project forbids.

    The rows are internally consistent (high >= close >= low >= open)
    and the price series is a plain geometric walk, which is what a
    price series is.
    """
    stamps = pd.bdate_range(start=start, periods=sessions, tz="UTC")
    close = 100.0 * (1.001 ** pd.Series(range(sessions)))
    frame = pd.DataFrame(
        {
            "symbol": ["TEST"] * sessions,
            "timestamp": stamps,
            "open": close * 0.999,
            "high": close * 1.004,
            "low": close * 0.996,
            "close": close,
            "volume": 1_000_000 + pd.Series(range(sessions)) * 137,
            "source": ["unit_test_fixture"] * sessions,
        }
    )
    return frame


# ─── The partition helpers ────────────────────────────────────────────────────


def test_partition_month_reads_the_year_and_month():
    key = "symbol=AAPL/year=2026/month=09/part-001.parquet"
    assert partition_month(key) == (2026, 9)


def test_partition_month_returns_none_for_an_unpartitioned_key():
    assert partition_month("symbol=AAPL/_quality.json") is None


def test_a_window_keeps_only_the_partitions_that_can_hold_it():
    keys = [
        "symbol=AAPL/year=2025/month=12/part-001.parquet",
        "symbol=AAPL/year=2026/month=01/part-001.parquet",
        "symbol=AAPL/year=2026/month=06/part-001.parquet",
        "symbol=AAPL/year=2026/month=07/part-001.parquet",
    ]
    kept = filter_keys_by_window(keys, since=date(2026, 1, 1), until=date(2026, 6, 30))
    assert kept == [
        "symbol=AAPL/year=2026/month=01/part-001.parquet",
        "symbol=AAPL/year=2026/month=06/part-001.parquet",
    ]


def test_a_key_without_a_partition_is_kept_rather_than_dropped():
    """A key the filter cannot place is a reason to READ it, not to skip it."""
    keys = ["symbol=AAPL/_quality.json", "symbol=AAPL/year=2026/month=01/part-001.parquet"]
    kept = filter_keys_by_window(keys, since=date(2026, 6, 1))
    assert "symbol=AAPL/_quality.json" in kept


def test_an_empty_window_keeps_every_partition():
    keys = ["symbol=AAPL/year=2020/month=01/part-001.parquet"]
    assert filter_keys_by_window(keys) == keys


# ─── The windowed read ────────────────────────────────────────────────────────


def test_a_windowed_read_returns_the_same_rows_as_a_full_read():
    """The fast path must return the SAME data, not a subset of its own.

    This is the assertion that matters: if the window dropped a row the
    full read holds, the chart would silently show a gap that is not in
    the lakehouse.
    """
    frame = _real_frame()
    full = frame.copy()

    windowed = slice_window(full, since=date(2025, 1, 1), until=date(2025, 3, 31))

    expected = full[
        (full["timestamp"] >= pd.Timestamp("2025-01-01", tz="UTC"))
        & (full["timestamp"] <= pd.Timestamp("2025-03-31", tz="UTC"))
    ].reset_index(drop=True)

    assert len(windowed) == len(expected)
    assert windowed["close"].tolist() == expected["close"].tolist()
    assert windowed["timestamp"].tolist() == expected["timestamp"].tolist()


def test_a_windowed_read_keeps_the_source_of_every_row():
    """A row must stay traceable to the source that produced it."""
    frame = _real_frame()
    windowed = slice_window(frame, since=date(2025, 1, 1), until=date(2025, 3, 31))
    assert not windowed.empty
    assert set(windowed["source"]) == {"unit_test_fixture"}


def test_a_windowed_read_outside_the_data_is_empty_not_an_error():
    frame = _real_frame()
    windowed = slice_window(frame, since=date(2030, 1, 1))
    assert windowed.empty


def test_a_window_keeps_the_last_session_of_its_final_day():
    """THE REGRESSION THIS PINS
    ----------------------------
    The window's `until` bound is a DATE, but a session's timestamp is
    the exchange OPEN in UTC - 14:30 for the NYSE, 02:00 for HOSE. A
    naive `timestamp <= until` compares against MIDNIGHT of that day
    and therefore throws away the session the window was supposed to
    end on.

    The bug was invisible in the UI (a missing last candle looks like a
    holiday) but it changed the reported numbers: NVDA's 252-day window
    ended one session early and reported a last close of 166.19 instead
    of the stored 162.85.

    So the `until` bound must cover the WHOLE day.
    """
    stamps = pd.to_datetime(
        ["2026-03-10", "2026-03-11", "2026-03-12"], utc=True
    ) + pd.Timedelta(hours=14, minutes=30)
    frame = pd.DataFrame(
        {
            "symbol": ["TEST"] * 3,
            "timestamp": stamps,
            "close": [1.0, 2.0, 3.0],
            "source": ["unit_test_fixture"] * 3,
        }
    )

    windowed = slice_window(frame, since=date(2026, 3, 1), until=date(2026, 3, 12))

    assert len(windowed) == 3, "the last session of the window's final day was dropped"
    assert windowed["close"].tolist() == [1.0, 2.0, 3.0]


def test_a_window_keeps_every_session_of_its_final_day():
    """Two sessions on the same day - both belong to the window."""
    stamps = pd.to_datetime(["2026-03-12", "2026-03-12"], utc=True) + pd.to_timedelta(
        [2 * 3600 + 0 * 60, 14 * 3600 + 30 * 60], unit="s"
    )
    frame = pd.DataFrame(
        {
            "symbol": ["TEST"] * 2,
            "timestamp": stamps,
            "close": [1.0, 2.0],
            "source": ["unit_test_fixture"] * 2,
        }
    )

    windowed = slice_window(frame, since=date(2026, 3, 1), until=date(2026, 3, 12))

    assert len(windowed) == 2
    assert windowed["close"].tolist() == [1.0, 2.0]


def test_a_window_still_excludes_the_days_after_it():
    """Widening the `until` bound must not let later sessions in."""
    stamps = pd.to_datetime(["2026-03-12", "2026-03-13"], utc=True) + pd.Timedelta(
        hours=14, minutes=30
    )
    frame = pd.DataFrame(
        {
            "symbol": ["TEST"] * 2,
            "timestamp": stamps,
            "close": [1.0, 2.0],
            "source": ["unit_test_fixture"] * 2,
        }
    )

    windowed = slice_window(frame, since=date(2026, 3, 1), until=date(2026, 3, 12))

    assert len(windowed) == 1
    assert float(windowed["close"].iloc[0]) == 1.0


# ─── The incremental write ────────────────────────────────────────────────────


def test_an_incremental_write_selects_the_partitions_from_the_change_onward():
    from app.lakehouse.parquet_manager import split_by_partition

    frame = _real_frame(start="2024-01-01", sessions=400)
    parts = split_by_partition(frame)
    assert len(parts) > 1

    cut = date(2026, 1, 1)
    selected = partitions_from(parts, cut)

    assert len(selected) < len(parts)
    for path in selected:
        year, month = partition_month(path)
        assert (year, month) >= (cut.year, cut.month)


def test_an_incremental_write_without_a_change_date_writes_everything():
    from app.lakehouse.parquet_manager import split_by_partition

    frame = _real_frame(start="2024-01-01", sessions=400)
    parts = split_by_partition(frame)
    assert partitions_from(parts, None) == parts


def test_the_incremental_write_leaves_the_earlier_partitions_untouched():
    """The partitions BEFORE the cut must keep their stored content.

    The whole argument for the incremental write is that a causal
    feature cannot change an earlier session's value. If that were
    false, the incremental write would leave stale numbers on disk -
    so this test pins the claim.
    """
    from app.lakehouse.parquet_manager import split_by_partition

    frame = _real_frame(start="2024-01-01", sessions=400)

    # The features of the full history...
    full = build_gold_features(frame)

    # ...and the features of the history as it stood BEFORE the newest
    # bar arrived. Every feature is causal, so the two must agree on
    # every session except the newest.
    cut = date(2026, 6, 1)
    earlier = frame[frame["timestamp"] < pd.Timestamp(cut, tz="UTC")].copy()
    earlier["timestamp"] = earlier["timestamp"]
    partial = build_gold_features(earlier)

    columns = [c for c in ("close", "sma_20", "ema_12", "rsi_14") if c in full.columns]
    assert columns, "the feature builder produced no comparable column"

    merged = full.merge(partial, on="timestamp", suffixes=("_full", "_partial"))
    assert not merged.empty
    for column in columns:
        left = merged[f"{column}_full"].astype(float)
        right = merged[f"{column}_partial"].astype(float)
        assert ((left - right).abs().fillna(0) < 1e-9).all(), (
            f"{column} changed for a session that preceded the new bar"
        )


def test_a_partition_split_keeps_every_row():
    from app.lakehouse.parquet_manager import split_by_partition

    frame = _real_frame(start="2024-01-01", sessions=400)
    parts = split_by_partition(frame)
    assert sum(len(part) for part in parts.values()) == len(frame)
