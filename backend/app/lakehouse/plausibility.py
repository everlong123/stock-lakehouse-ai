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
#:
#: WHY THIS IS NOT ABSOLUTE
#: -----------------------
#: This floor was originally absolute, and it silently ate real data. ACH
#: trades around $0.21 on NYSE American, and every bar for it since
#: 2026-10-23 was rejected: "All incoming rows failed the plausibility
#: screen; nothing written." The symbol was frozen at its 2026-10-22 close
#: while the provider had newer bars.
#:
#: A sub-unit price is not evidence of corruption - it is evidence of a
#: cheap instrument. What IS evidence of corruption is a price that
#: disagrees with the symbol's OWN recent level, and that is what the
#: magnitude check below measures. So the floor is applied only when it
#: cannot contradict the symbol's own history: see
#: :func:`_effective_floor`.
MIN_PLAUSIBLE_PRICE = 0.5

#: The floor applied to a symbol whose own recent level is itself sub-unit.
#: It exists only to reject a row that is zero-ish or negative; the real
#: defence for such a symbol is the magnitude check, which compares the row
#: against the symbol's recent close.
MIN_SUBUNIT_PRICE = 1e-6

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

#: How many of the symbol's newest stored partitions are sampled to establish
#: its price level.
#:
#: More than one partition is needed because a symbol that has just been split
#: or that has fallen steeply keeps pre-event bars in its newest partition. If
#: only the newest partition were read, the sample would be dominated by those
#: stale bars and the reference would sit far above the symbol's actual level.
REFERENCE_PARTITION_SAMPLE = 3

#: A symbol's price level is described by TWO numbers, because the two checks
#: that use it ask different questions.
#:
#: ``floor`` is the LOW end of the recent range. It answers "is this symbol a
#: cheap instrument?", which is what decides whether the absolute price floor
#: of 0.5 may be relaxed. Using the median here hides the answer: PARA's
#: newest partition still holds pre-split bars around 2.72, so its median is
#: ~2.21 while its real level is ~0.42 - and with 2.21 as the floor reference
#: the genuine 0.425 bar was rejected as ``implausible_open``.
#:
#: ``magnitude`` is the MEDIAN of the recent range. It answers "is this price
#: wildly far from where this symbol trades?", which is what catches a unit
#: error. Using the low end here would be wrong in the opposite direction:
#: PARA traded near $102 in 2021 and near $0.47 in 2026, so the low end is
#: ~200x below the median, and a 200x legitimate move would be rejected as
#: ``price_magnitude`` - deleting real history to catch a rare unit bug.
#:
#: A unit error is 1000x off, which is far outside both references' tolerance
#: bands, so splitting the two costs the guard nothing.
ReferenceLevel = dict[str, dict[str, float]]

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


def _effective_floor(
    row: pd.Series,
    reference_prices: ReferenceLevel | dict[str, float] | None,
) -> float:
    """The lowest price this row may carry, given what the symbol itself trades at.

    WHY THIS IS SYMBOL-RELATIVE
    ---------------------------
    An absolute floor of 0.5 rejects ACH, a NYSE American listing that trades
    near $0.21. Measured on 2026-11-04: ACH's last stored close was 0.21
    (2026-10-22), Yahoo was already serving 0.28, and every bar since was
    dropped - the symbol sat frozen at 2026-10-22 while the provider moved
    on. The auto-refresh reported it as "All incoming rows failed the
    plausibility screen; nothing written."

    A cheap instrument is not a corrupt one. The evidence of corruption is a
    price that contradicts the symbol's OWN recent level, and that is what the
    magnitude check measures. So:

      * If the symbol's own recent level is at or above the absolute floor,
        the floor applies unchanged - a sub-0.5 row really is a unit error.
      * If the symbol's own level is BELOW the floor, the symbol genuinely
        trades sub-unit, so the floor relaxes to a value that only rejects
        zero-ish numbers, and the magnitude check does the real work.
      * If there is no reference for the symbol, the absolute floor applies.
        That is the safe direction: without evidence either way, the stricter
        check wins.

    WHY THE FLOOR REFERENCE IS THE LOW END OF THE RECENT RANGE
    ----------------------------------------------------------
    The floor reference is the symbol's recent *minimum*, not its median,
    because the median hides the case that actually bites. PARA (a US
    micro-cap that has fallen from ~$4.90 to ~$0.42 over 2026) has a
    newest-partition median of ~2.21, because that partition still holds a
    handful of pre-split bars, while the symbol's true recent level is
    ~0.42.

    With a median of 2.21 as the reference, the absolute floor of 0.5 stays
    in force and the provider's real 0.425 bar is rejected as
    ``implausible_open``. The result is a bar that can never be corrected:
    the wrong value (4.251, from before a 10:1 split) is what the screen
    compares against, so the right value is always the one that looks
    impossible.

    The low end answers exactly this question - "is this symbol cheap?" - and
    the magnitude check (which uses the median, separately) is what catches
    a real unit error.
    """
    symbol = row.get("symbol")
    if reference_prices and symbol is not None:
        level = reference_prices.get(str(symbol).upper())
        if level is not None:
            reference = level.get("floor") if isinstance(level, dict) else level
            if reference is not None and 0 < reference < MIN_PLAUSIBLE_PRICE:
                return MIN_SUBUNIT_PRICE
    return MIN_PLAUSIBLE_PRICE


def _reason_for(
    row: pd.Series,
    now: pd.Timestamp,
    reference_prices: ReferenceLevel | dict[str, float] | None = None,
) -> str | None:
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

    floor = _effective_floor(row, reference_prices)

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
        if value < floor:
            # Sub-unit prices are what a double /1000 on a VND quote looks
            # like - but only for a symbol that does NOT itself trade sub-unit.
            # A symbol whose own level is sub-unit (ACH at ~$0.21) gets the
            # relaxed floor; see _effective_floor.
            return f"implausible_{col}"

    return None


def _magnitude_reason(
    row: pd.Series,
    reference_prices: ReferenceLevel | dict[str, float] | None,
) -> str | None:
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
    level = reference_prices.get(str(symbol).upper())
    if level is None:
        return None
    # The magnitude check uses the MEDIAN of the symbol's recent range, not
    # the low end. The two checks ask different questions and must not share
    # one number:
    #
    #   floor     -> "is this symbol cheap?"  -> LOW end
    #   magnitude -> "is this price wildly off?" -> MEDIAN
    #
    # Using the low end for the magnitude check would reject real history.
    # PARA traded near $102 in 2021 and near $0.47 in 2026, so its low end
    # sits ~200x below its median; a 200x legitimate move would be rejected
    # as ``price_magnitude``. A unit error, which is what this check exists
    # for, is 1000x off - far outside the band either reference produces.
    if isinstance(level, dict):
        reference = level.get("magnitude")
    else:
        reference = level
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
    reference_prices: ReferenceLevel | dict[str, float] | None = None,
) -> tuple[pd.DataFrame, PlausibilityReport]:
    """Drop rows that cannot possibly be real market data.

    Returns the surviving rows plus a :class:`PlausibilityReport`. Rows are
    never repaired - a row with an unknown-correct value is discarded, because
    guessing would put invented prices into the lake.

    ``reference_prices`` maps symbol -> its recent price level and enables the
    cross-check that catches unit errors (a VND price divided by 1000). Each
    symbol's level carries two numbers: ``floor`` (the low end of the recent
    range, used to relax the absolute price floor for a cheap instrument) and
    ``magnitude`` (the median, used to catch a price that is wildly off). A
    plain float is also accepted and is used for both. Symbols absent from the
    mapping get only the self-contained checks, so the screen degrades safely
    rather than rejecting everything.
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
        reason = _reason_for(row, clock, reference_prices)
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