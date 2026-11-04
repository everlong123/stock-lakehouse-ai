"""Plausibility guard for incoming Bronze rows.

Why this exists
---------------
Bronze accepted whatever the streaming publishers pushed, so a parser bug
became permanent lake corruption. The concrete failure:

    VCB  source=vn_ws   ts=1970-01-10 19:15  close=56.9
    VCB  source=vn_rest ts=2026-10-13 02:15  close=56600

Both rows claimed to be VCB. The WS row was wrong on two axes at once: a 56.9
VND price for a stock that trades near 56,000, and a timestamp 56 years before
the ingestion time. ``ssi_vn_provider`` and ``vn_rest_poller`` multiply by
1000 correctly; ``vn_websocket.parse_quote`` divides by 1000, and its
``IDX_LAST_UPDATED`` field appears to index the wrong column. The publisher
publishes whatever the parser produced, and the consumer writes it straight to
Bronze.

Rather than guess the correct field offsets - which requires a live capture
during VN trading hours and guessing in the meantime would risk corrupting
good data - this module rejects rows that are *provably* impossible. The
predicate is deliberately narrow:

  * a timestamp outside [MIN_TIMESTAMP, ingestion_time + tolerance], or
  * a non-positive price, or
  * a price that contradicts the symbol's own recent history by orders of
    magnitude (a 1000x error is the signature seen here).

The last rule needs care: comparing against history makes Bronze
state-dependent, which would make a replay non-deterministic. So the
self-contained checks live here, and the magnitude check is applied with an
explicit per-symbol reference passed by the caller.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from app.core.logging_config import get_logger

logger = get_logger(__name__)

#: No equity series in this lakehouse legitimately starts before 2000. The
#: observed corruption sat at the UNIX epoch (1970-01-01), which is where a
#: wrong field index lands when it reads a small integer like a side flag or a
#: match count.
MIN_TIMESTAMP = pd.Timestamp("2000-01-01", tz="UTC")

#: How far ahead of the ingestion clock a timestamp may sit before it is
#: treated as corrupt. Ten minutes absorbs clock skew and bars published for
#: the minute that is still forming.
MAX_FUTURE_SKEW = pd.Timedelta(minutes=10)

#: A price this small cannot be a real equity or VN share. VCB trades near
#: 56,000 VND; the corrupt row carried 56.9.
MIN_PLAUSIBLE_PRICE = 0.5

#: A price may not differ from the symbol's own recent history by more than
#: this factor. This catches unit errors that a self-contained check cannot:
#: VCB wrote close=56.9 while its true price was 56,600, a factor of 1000.
#: The margin is deliberately wide (100x) so a genuine split, a rights issue
#: or a newly listed instrument is not deleted - those produce much smaller
#: ratios than a unit bug, and a wrongly deleted real bar is far more costly
#: than a bad row surviving one pass.
MAX_PRICE_DEVIATION_FACTOR = 100.0

#: Number of recent rows used to establish a symbol's price level.
PRICE_REFERENCE_SAMPLE = 50

#: A STREAMING row (one of the per-second bars the Kafka publishers emit)
#: must sit close to its own symbol's price level. Unlike a historical daily
#: bar, an intraday tick has no excuse for being far away from the last
#: traded price: the two describe the SAME session.
#:
#: This tighter factor exists because of a measured symbol-mapping failure.
#: On 2026-10-07 the Finnhub WebSocket publisher attributed trades to the
#: wrong ticker, and Bronze stored them under the wrong symbol:
#:
#:     symbol   stored close range   true close that day
#:     NVDA     855 .. 1938           237.47
#:     TSLA      68 ..  283           377.81
#:     COIN      72 ..  125           178.45
#:     BTC-USD 48072 .. 97762         83275.93
#:
#: The values are genuine trades from OTHER tickers (the series is internally
#: continuous, so it is not random noise), so the 100x magnitude check below
#: did not fire for the milder cases and the wrong price reached the chart.
#: A streaming row whose price is more than this factor away from its own
#: symbol's level is rejected outright.
#:
#: 2.5x is deliberately tight: a real intraday tick of a liquid name never
#: moves that far from the previous session's close, and a legitimate 2:1
#: split would be corrected by the daily provider anyway.
STREAM_PRICE_DEVIATION_FACTOR = 2.5

#: Sources whose rows are per-second / per-minute intraday prints. These are
#: held to the tighter deviation factor because they describe the SAME
#: session as the symbol's last stored close.
INTRADAY_STREAM_SOURCES = frozenset(
    {
        "finnhub_ws",
        "finnhub_rest",
        "vn_ws",
        "vn_rest",
        "kafka",
        "manual",
    }
)


@dataclass
class PlausibilityReport:
    """Outcome of a plausibility pass over a candidate Bronze batch."""

    accepted_rows: int = 0
    rejected_rows: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    samples: list[dict] = field(default_factory=list)

    @property
    def has_rejections(self) -> bool:
        return self.rejected_rows > 0

    def to_dict(self) -> dict:
        return {
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "reasons": dict(self.reasons),
        }


def _reason_for(row: pd.Series, now: pd.Timestamp) -> str | None:
    """Return why ``row`` is impossible, or ``None`` if it looks real."""

    ts = row.get("timestamp")
    if ts is None or pd.isna(ts):
        return "null_timestamp"
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    if ts < MIN_TIMESTAMP:
        return "epoch_timestamp"
    if ts > now + MAX_FUTURE_SKEW:
        return "future_timestamp"

    price_cols = [c for c in ("open", "high", "low", "close") if c in row.index]
    for col in price_cols:
        value = row.get(col)
        if value is None or pd.isna(value):
            return f"missing_{col}"
        try:
            value = float(value)
        except (TypeError, ValueError):
            return f"nonnumeric_{col}"
        if value <= 0:
            return f"nonpositive_{col}"
        if value < MIN_PLAUSIBLE_PRICE:
            # Sub-unit prices are what a double /1000 on a VND quote looks
            # like. US equities never trade below a cent.
            return f"implausible_{col}"

    return None


def _magnitude_reason(row: pd.Series, reference_prices: dict[str, float] | None) -> str | None:
    """Reject a price that contradicts the symbol's own recent level.

    This is the check that catches a VND quote divided by 1000: VCB's recent
    close is ~56,600 and a 56.9 row is three orders of magnitude away. The
    threshold is intentionally loose (100x) so that legitimate discontinuities -
    splits, rights issues, a symbol relisted under a different scale - are not
    deleted. Deleting real history to catch a rare unit bug is a bad trade.

    STREAMING rows (per-second prints) are held to a much tighter factor,
    because they describe the same session as the symbol's last stored close
    and therefore cannot legitimately sit far away from it. See
    :data:`STREAM_PRICE_DEVIATION_FACTOR` for the measured case this catches.
    """
    if not reference_prices:
        return None
    symbol = row.get("symbol")
    if symbol is None:
        return None
    reference = reference_prices.get(str(symbol).upper())
    if reference is None or reference <= 0:
        return None

    close = row.get("close")
    if close is None or pd.isna(close):
        return None
    try:
        close = float(close)
    except (TypeError, ValueError):
        return "nonnumeric_close"
    if close <= 0:
        return None

    ratio = reference / close
    if ratio > MAX_PRICE_DEVIATION_FACTOR or (1.0 / ratio) > MAX_PRICE_DEVIATION_FACTOR:
        return "price_magnitude"

    # A streaming tick far from its own symbol's level is a SYMBOL MAPPING
    # failure, not a unit error. The factor is much tighter here because both
    # numbers describe the same session.
    source = str(row.get("source", "")).strip().lower()
    if source in INTRADAY_STREAM_SOURCES:
        tight = reference / close
        if tight > STREAM_PRICE_DEVIATION_FACTOR or (1.0 / tight) > STREAM_PRICE_DEVIATION_FACTOR:
            return "stream_price_deviation"
    return None


def screen_batch(
    frame: pd.DataFrame,
    now: pd.Timestamp | None = None,
    reference_prices: dict[str, float] | None = None,
) -> tuple[pd.DataFrame, PlausibilityReport]:
    """Drop rows that cannot possibly be real market data.

    Returns the surviving rows plus a :class:`PlausibilityReport`. Rows are
    never repaired - a row with an unknown-correct value is discarded, because
    guessing would put invented prices into the lake.

    ``reference_prices`` maps symbol -> typical recent close and enables the
    cross-check that catches unit errors (a VND price divided by 1000). Symbols
    absent from the mapping get only the self-contained checks, so the screen
    degrades safely rather than rejecting everything.
    """
    report = PlausibilityReport()
    if frame.empty:
        return frame, report

    clock = now or pd.Timestamp.now(tz="UTC")
    if clock.tzinfo is None:
        clock = clock.tz_localize("UTC")

    # Work on a prepared copy so timestamp comparisons are tz-aware regardless
    # of what the caller passed in.
    prepared = frame.copy()
    if "timestamp" in prepared.columns:
        prepared["timestamp"] = pd.to_datetime(prepared["timestamp"], utc=True, errors="coerce")

    reasons: list[str | None] = []
    for _, row in prepared.iterrows():
        reason = _reason_for(row, clock)
        if reason is None:
            reason = _magnitude_reason(row, reference_prices)
        reasons.append(reason)

    rejected = pd.Series([r is not None for r in reasons], index=prepared.index)
    report.accepted_rows = int((~rejected).sum())
    report.rejected_rows = int(rejected.sum())

    for reason in reasons:
        if reason:
            report.reasons[reason] = report.reasons.get(reason, 0) + 1

    if report.has_rejections:
        bad = prepared.loc[rejected]
        keep_cols = [c for c in ("symbol", "timestamp", "close", "source", "ingestion_time") if c in bad.columns]
        for record in bad[keep_cols].head(5).to_dict("records"):
            sample = {k: (str(v) if pd.notna(v) else None) for k, v in record.items()}
            sample["reason"] = next(r for r, flag in zip(reasons, rejected) if flag)
            report.samples.append(sample)
        logger.warning(
            "Plausibility screen rejected %s/%s rows: %s",
            report.rejected_rows,
            len(prepared),
            report.reasons,
        )

    return frame.loc[~rejected].copy(), report