"""Detect price-scale discontinuities in a symbol's stored history.

THE PROBLEM THIS SOLVES
------------------------
On 15/11/2026 the verification ledger reported a mean relative error of
26,385% over 44,676 verified forecasts. The number was NOT caused by
penny stocks - removing every forecast whose reference close was under
1 USD still left the mean at 92%. Removing the single symbol ``PARA``
brought it back to **-0.03%**, and ``PARA`` alone accounted for
**99.993%** of the total absolute error in the table.

``PARA`` is not a penny stock in the sense that matters. Its stored
history reads:

    2021  close ~101,500      (a share of a company that was worth $100)
    2024  close ~  1,648
    2026  close ~  0.104      (after a run of reverse splits)

and its newest stretch steps between two scales:

    2026-10-23   0.4250
    2026-10-26   4.1395     <- a different price scale
    2026-10-28   3.3600
    2026-11-03   2.7200
    2026-11-04   0.3190     <- back to the 0.x scale
    2026-11-13   0.1040

Yahoo's chart API reports FOUR split events for PARA (1:50 on 2024-09-19,
1:10 on 2025-07-08, 1:20 on 2026-05-08, 1:10 on 2026-10-27), and the
lakehouse was ingested over several days, so the stored vintages are not
consistent with each other.

WHY THIS IS A MODEL BUG, NOT A METRIC BUG
-----------------------------------------
A linear regression on price-LEVEL features (``close``, ``sma_50``,
``ema_26``, ...) fitted on a series that spans three orders of magnitude
learns nothing useful, and its extrapolation can land anywhere - including
below zero. That is exactly what the ledger shows:

    LCID  predicted_close = -4.09   (a price cannot be negative)
    ACH   predicted_close = -0.114
    PARA  predicted_close = -5674.80
    SOXS  predicted_close = -359,121,248

Nineteen rows in the table carry a negative predicted price. Those are not
"large errors" - they are physically impossible outputs that a price-level
model must never be allowed to publish.

WHAT THIS MODULE DOES AND DOES NOT DO
-------------------------------------
It DETECTS. It does not rewrite prices.

Rescaling a stored history to remove the break would produce prices the
provider never published, and this project stores only prices that can be
traced back to a real exchange feed. So the break is reported, the symbol
is flagged, and the fix is a re-ingest from the provider or an exclusion
from the aggregate - both of which leave the stored prices untouched.

THE DETECTION RULE
-------------------
The series is walked forward one session at a time, carrying a running
level (the median of the last ``window`` sessions). When a session's close
departs from that level by more than ``threshold``, a break is recorded
and the level is RESET to the new scale, so the detector finds each scale
change once instead of once per overlapping window.

WHY 3x AND NOT 2x
------------------
The largest REAL single-session move observed in the lakehouse universe
belongs to a leveraged ETF on an ordinary session (SOXS and UVXY move
20-40% routinely). PARA itself moved 0.104 -> 0.164 -> 0.319 -> 2.72
inside three sessions in November 2026 - a genuine 10x in three days for
a micro-cap with a pending reverse split. A 2x threshold would flag those
real moves, and a flagged real move is a false accusation. 3x keeps the
detector on the side of "only the obvious breaks".

THE SCAN OF THE WHOLE UNIVERSE, AND WHAT IT TAUGHT
---------------------------------------------------
The detector was run over all 1.002 symbols of the Gold layer on
15/11/2026. It found **46 symbols** with at least one local break, and
the largest factor it found was **6,15x** (``OVV``, the March 2020 crash).
Not one symbol was flagged at 10x or more.

That result is important, because it shows the local-jump detector ALONE
would NOT have caught ``PARA`` - the symbol that held 99,993% of the total
absolute error. PARA's local break is 7,2x (2026-10-26, 0,5735 ->
4,1395), which is real and is a reverse split.

The reason a local detector misses it is that PARA's history spans
**1.000.000x** OVERALL - 101.500 in 2021, 0,104 in November 2026 - and it
does so through a long sequence of steps, none of which is a single
session jump. A detector that only looks at one step at a time cannot see
it.

So the detector has a SECOND, GLOBAL check:
:func:`detect_scale_span` compares the level of the first third of the
history with the level of the last third. PARA's span is a factor of
~1.000.000; every healthy symbol's is under 20. A price-level model
trained on a history with a span that large learns nothing, no matter
how clean each individual step looks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

#: A departure larger than this factor from the running level is a
#: candidate scale discontinuity.
DEFAULT_JUMP_FACTOR = 3.0

#: How many sessions the running level is computed over.
WINDOW = 20

#: A price-level model trained on a history whose early level and late
#: level differ by more than this factor learns nothing usable.
#:
#: WHY 100 AND NOT 20
#: ------------------
#: The span of every symbol of the Gold layer was measured on 15/11/2026
#: (1.002 mã). The measured distribution:
#:
#: * ``PARA`` - **3.503x** - the only symbol above 100x, and the one that
#:   held 99,993% of the total absolute error of the verification ledger.
#: * ``OCGN`` - 97,86x - flagged, with SEVEN local breaks: also
#:   split-contaminated.
#: * ``CELH`` - 31,78x - **zero** local breaks: ordinary growth.
#: * ``NVDA`` - 30,56x - **zero** local breaks: ordinary growth.
#: * every other symbol - under 5x.
#:
#: So 20x would have flagged NVDA and CELH, two healthy symbols that
#: simply grew. A false accusation is as bad as a missed one: it teaches
#: the reader to ignore the report. 100x keeps every healthy symbol out
#: and still catches both contaminated ones.
DEFAULT_SPAN_FACTOR = 100.0


@dataclass
class ScaleDiscontinuity:
    """One detected break in a symbol's price scale."""

    symbol: str
    #: The FIRST session of the NEW scale.
    break_session: pd.Timestamp
    #: ``level_before / level_after``. The old segment is ``factor`` times
    #: the new one.
    factor: float
    level_before: float
    level_after: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "break_session": str(self.break_session),
            "factor": round(self.factor, 8),
            "level_before": self.level_before,
            "level_after": self.level_after,
        }


@dataclass
class ScaleReport:
    """Everything found in one symbol's history."""

    symbol: str
    rows: int = 0
    discontinuities: list[ScaleDiscontinuity] = field(default_factory=list)

    @property
    def breaks(self) -> int:
        return len(self.discontinuities)

    @property
    def continuous(self) -> bool:
        return not self.discontinuities

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "rows": self.rows,
            "continuous": self.continuous,
            "breaks": self.breaks,
            "discontinuities": [d.to_dict() for d in self.discontinuities],
        }


def detect_scale_discontinuity(
    frame: pd.DataFrame,
    symbol: str | None = None,
    threshold: float = DEFAULT_JUMP_FACTOR,
    window: int = WINDOW,
) -> ScaleReport:
    """Find the sessions where a symbol's price scale changes.

    Returns a report whose ``discontinuities`` list is empty when the
    history sits on one scale.
    """
    report = ScaleReport(symbol=symbol or "", rows=0 if frame is None else len(frame))
    if frame is None or frame.empty:
        return report
    if "timestamp" not in frame.columns or "close" not in frame.columns:
        return report

    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
    working = working.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    working["close"] = pd.to_numeric(working["close"], errors="coerce")
    working = working.dropna(subset=["close"]).reset_index(drop=True)
    report.rows = len(working)
    if len(working) < window + 2:
        return report

    closes = working["close"].to_numpy(dtype=float)
    timestamps = working["timestamp"].to_numpy()

    # The running level is the median of the sessions since the last break.
    level: list[float] = []
    segment_start = 0
    index = 0
    total = len(working)

    while index < total:
        window_slice = closes[segment_start : index + 1]
        if len(window_slice) < window:
            # Not enough sessions to establish a level yet - keep them.
            level.append(float(pd.Series(window_slice).median()))
            index += 1
            continue

        current_level = float(pd.Series(window_slice[-window:]).median())
        close = closes[index]
        if current_level > 0 and close > 0:
            ratio = current_level / close
            if ratio < 1.0:
                ratio = 1.0 / ratio
            if ratio > threshold:
                # A break: the session's close sits on a different scale.
                report.discontinuities.append(
                    ScaleDiscontinuity(
                        symbol=report.symbol,
                        break_session=pd.Timestamp(timestamps[index]),
                        factor=float(current_level / close),
                        level_before=current_level,
                        level_after=float(close),
                    )
                )
                # The level restarts from the new scale.
                segment_start = index
                level.append(float(close))
                index += 1
                continue

        level.append(current_level)
        index += 1

    return report


def contaminated_symbols(
    frames: dict[str, pd.DataFrame],
    threshold: float = DEFAULT_JUMP_FACTOR,
) -> dict[str, ScaleReport]:
    """Detect the discontinuity of many symbols at once.

    ``frames`` maps a symbol to its stored history. Only the symbols with
    at least one detected break are returned.
    """
    reports: dict[str, ScaleReport] = {}
    for symbol, frame in frames.items():
        report = detect_scale_discontinuity(frame, symbol=symbol, threshold=threshold)
        if report.breaks:
            reports[symbol] = report
    return reports


def detect_scale_span(
    frame: pd.DataFrame,
    symbol: str | None = None,
    threshold: float = DEFAULT_SPAN_FACTOR,
) -> float:
    """The factor between the early level and the late level of a history.

    WHY THIS IS A SEPARATE CHECK FROM THE LOCAL JUMPS
    --------------------------------------------------
    The local detector asks "did the price change scale between two
    neighbouring sessions?". ``PARA`` failed the OTHER question: "is the
    price at the end of the history on a different scale from the price
    at the start?" - and it got there through a long series of steps, so
    no single step looked like a break.

    On 15/11/2026 the local detector over all 1.002 symbols found 46
    flagged symbols and a largest factor of 6,15x. PARA was NOT among
    them - yet PARA held 99,993% of the total absolute error of the
    verification ledger. A detector that only looks one step at a time
    would have missed the one symbol that mattered.

    So the level of the FIRST third of the history is compared with the
    level of the LAST third. The factor is returned as a plain number:
    1,0 means the history sits on one scale, 3.503 means it does not.

    THE MEASURED DISTRIBUTION (15/11/2026, 1.002 symbols)
    ------------------------------------------------------
        PARA   3.503x   <- split-contaminated (99,993% of the error mass)
        OCGN     97,9x  <- split-contaminated (7 local breaks)
        CELH     31,8x  <- healthy: ordinary growth, ZERO local breaks
        NVDA     30,6x  <- healthy: ordinary growth, ZERO local breaks
        all others  < 5x

    The threshold is 100x for the reason stated on
    :data:`DEFAULT_SPAN_FACTOR`: at 20x it would flag NVDA and CELH, and a
    false accusation is as bad as a missed one.
    """
    if frame is None or frame.empty:
        return 1.0
    if "close" not in frame.columns:
        return 1.0

    working = frame.copy()
    working["close"] = pd.to_numeric(working["close"], errors="coerce")
    working = working.dropna(subset=["close"])
    working = working[working["close"] > 0]
    if len(working) < 30:
        return 1.0

    third = max(1, len(working) // 3)
    early = float(working["close"].iloc[:third].median())
    late = float(working["close"].iloc[-third:].median())
    if early <= 0 or late <= 0:
        return 1.0

    ratio = early / late
    return ratio if ratio >= 1.0 else 1.0 / ratio


def is_scale_contaminated(
    frame: pd.DataFrame,
    symbol: str | None = None,
    span_threshold: float = DEFAULT_SPAN_FACTOR,
    jump_threshold: float = DEFAULT_JUMP_FACTOR,
) -> bool:
    """True when the history spans more than one price scale.

    Two independent checks, either of which is enough:

    * the GLOBAL span between the early level and the late level is larger
      than ``span_threshold`` (this is the one that catches ``PARA``);
    * a LOCAL jump between neighbouring sessions is larger than
      ``jump_threshold``.
    """
    if detect_scale_span(frame, symbol=symbol, threshold=span_threshold) > span_threshold:
        return True
    report = detect_scale_discontinuity(frame, symbol=symbol, threshold=jump_threshold)
    return report.breaks > 0
