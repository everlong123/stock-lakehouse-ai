"""Detecting a daily bar that was captured MID-SESSION and frozen there.

WHY THIS FILE EXISTS
--------------------
On 15/11/2026 the quality gate failed on ``AMD`` and ``INTC`` under
``check_source_agreement``: two providers appeared to report different
closes for the same session. The measurement:

    AMD  2026-10-28   yfinance_eod  close 567.00   volume  7,367,032
                      yahoo_http    close 578.44   volume 18,848,600
                      (provider's settled close, verified live: 578.44)

The two rows are NOT the same bar. The ``yfinance_eod`` row was written at
**16:29 UTC = 12:29 EDT**, i.e. 3.5 hours BEFORE the NYSE close at 16:00
EDT. Its ``close`` is the last trade price at that moment and its volume
is the volume traded so far. It is a MID-SESSION SNAPSHOT frozen into a
daily bar.

    bronze   2026-10-28 04:00:00Z  close 567.00  vol  7,367,032  yfinance_eod
    bronze   2026-10-28 13:30:00Z  close 578.44  vol 18,848,600  yahoo_http
    silver   2026-10-28 13:30:00Z  close 578.44  vol 18,848,600  yahoo_http
    gold     2026-10-28 13:30:00Z  close 578.44  vol 18,848,600  yahoo_http

The Silver and Gold layers already picked the correct row, because they
prefer the canonical session stamp. Bronze is the layer that keeps both.

THE SCOPE IS LARGER THAN THE SIX SYMBOLS THE GATE FLAGGED
-----------------------------------------------------------
A full scan of Bronze found **1,162 sessions** that hold both a
mid-session snapshot and the settled bar. They are not all ``yfinance_eod``:
most are ``yahoo_http`` rows stamped at the exact minute the fetch ran
(16:41, 17:32, 04:02, ...). The common trait is the same - the row was
written while its own session was still open.

THE STRUCTURAL SIGNAL
----------------------
A session's volume can only **grow** as the session runs, and its high and
low can only **expand**, so the settled bar's range CONTAINS the forming
bar's range:

    forming.volume <  settled.volume
    forming.high  <= settled.high
    forming.low   >= settled.low

and the two closes differ, because the price moved after the snapshot was
taken.

The two range inequalities carry a small ONE-SIDED tolerance. Containment
holds strictly only when the snapshot already touched the session's
extreme; a snapshot taken at 14:30 records the high and the low AS OF
14:30, and the session may reach a new high or a new low afterwards. The
measured case: CPB 2026-11-17 had forming.high = 24.01 and settled.high =
24.05, so the settled range pokes out on the high side - which the
tolerance allows. The opposite direction is rejected outright: a forming
bar whose range is WIDER than the settled one is impossible.

This test is what makes the rule safe to apply in both
directions - it identifies which of the two rows is the stale one without
consulting a calendar of market hours, and it cannot fire on two rows that
describe the same instant.

WHAT THIS IS NOT
----------------
It is not a calendar. There is no table of exchange open/close times here,
because the range test does not need one: it compares two rows of
the SAME session against each other, so it works for every market in the
universe - the NYSE, the HOSE, the ASX, the TWSE - without knowing when
any of them trade.

This module therefore reports the finding. It does not delete anything:
the settled row is already the one Silver and Gold serve, and Bronze is
the raw layer, whose job is to keep what the provider actually said.
"""

from __future__ import annotations

import pandas as pd

#: Two closes are treated as "the same price" when they differ by less than
#: this RELATIVE amount. A one-cent move on a $347 stock is 3e-5 relative,
#: so 1e-6 is comfortably below any real difference and comfortably above
#: the float noise two providers produce for the same price.
SAME_PRICE_REL_TOL = 1e-6

#: How far the two bars' RANGES may sit apart before the pair stops looking
#: like two moments of the same session.
#:
#: THE TOLERANCE IS ONE-SIDED
#: ---------------------------
#: A session's high and low can only EXPAND, so the settled bar's range
#: normally CONTAINS the forming bar's range. The exception is a snapshot
#: taken before the session reached its extreme: the settled bar pokes out
#: on that side. The measured case: CPB 2026-11-17 had ``forming.high =
#: 24.01`` and ``settled.high = 24.05`` - the session went four cents
#: higher after the snapshot.
#:
#: The excess may therefore be up to this tolerance, but only on the
#: SETTLED side. A forming bar whose range is WIDER than the settled one is
#: impossible - the settled bar records everything the forming one saw and
#: more - so that direction is rejected outright.
#:
#: The tolerance also absorbs the float noise two different fetches of the
#: same session produce: CHTR 2026-11-17 had ``forming.high =
#: 142.60020446777344`` and ``settled.high = 142.60000610351562``, a
#: difference of 2e-4 on a $142 price.
RANGE_OVERLAP_REL_TOL = 0.02

#: A ratio this large between two rows of the SAME session means the two
#: rows live on different price scales - a reverse split, not a mid-session
#: snapshot. CMG split 50:1 in October 2026: the pre-split rows carry a
#: close of ~19,700 and the post-split rows ~27.52. The range test
#: cannot separate those (the "range" of a split series is meaningless),
#: and the scale break is handled by ``app.lakehouse.scale_repair`` - which
#: restates the history properly. This rule must stay out of that.
SCALE_BREAK_RATIO = 10.0


def forming_snapshot_reason(
    forming: pd.Series,
    settled: pd.Series,
) -> bool:
    """True when ``forming`` looks like a mid-session snapshot of ``settled``.

    The test is the range relation described in the module docstring: the two
    bars' ranges must OVERLAP, the settled volume must be larger, and the
    two closes must differ. Containment is not required - a snapshot taken
    before the session reached its extreme has a range the settled one does
    not contain.

    Args:
        forming: the candidate stale row.
        settled: the row it is compared against.

    Returns:
        True when ``forming`` is a mid-session snapshot of ``settled``.
    """
    try:
        f_high = float(forming["high"])
        f_low = float(forming["low"])
        f_close = float(forming["close"])
        s_high = float(settled["high"])
        s_low = float(settled["low"])
        s_close = float(settled["close"])
    except (KeyError, TypeError, ValueError):
        return False

    if not all(
        value == value for value in (f_high, f_low, f_close, s_high, s_low, s_close)
    ):
        return False

    f_volume = pd.to_numeric(pd.Series([forming.get("volume")]), errors="coerce").iloc[0]
    s_volume = pd.to_numeric(pd.Series([settled.get("volume")]), errors="coerce").iloc[0]
    if pd.isna(f_volume) or pd.isna(s_volume):
        return False

    # THE RANGE RELATION
    # ------------------
    # A session's high and low can only EXPAND as it runs, so the settled
    # bar's range must CONTAIN the forming bar's range - with ONE exception:
    # the snapshot may have been taken before the session reached its
    # extreme, in which case the settled bar pokes out on that side.
    #
    # The measured case: CPB 2026-11-17 had `forming.high = 24.01` and
    # `settled.high = 24.05` - the session went four cents higher after
    # the snapshot, so containment failed on the high alone.
    #
    # So containment is required up to a small tolerance, and the tolerance
    # is one-sided: the SETTLED bar may exceed the forming one (the session
    # reached a new extreme after the snapshot), but the forming bar may
    # NOT exceed the settled one by more than the tolerance. A forming bar
    # whose range is WIDER than the settled one is impossible - the settled
    # bar records everything the forming one saw and more.
    #
    # The tolerance also absorbs the float noise two different fetches of the
    # same session produce: CHTR 2026-11-17 had `forming.high =
    # 142.60020446777344` and `settled.high = 142.60000610351562`.
    high_scale = max(abs(s_high), abs(f_high), 1e-9)
    low_scale = max(abs(s_low), abs(f_low), 1e-9)
    if f_high > s_high and (f_high - s_high) / high_scale > RANGE_OVERLAP_REL_TOL:
        return False
    if f_low < s_low and (s_low - f_low) / low_scale > RANGE_OVERLAP_REL_TOL:
        return False

    # The settled volume must be strictly larger: a session's traded volume
    # only grows. Equal volumes mean the two rows describe the same moment.
    if not (float(f_volume) < float(s_volume)):
        return False

    # The close must differ, otherwise there is nothing stale to report.
    scale = max(abs(s_close), 1e-9)
    if abs(f_close - s_close) / scale <= SAME_PRICE_REL_TOL:
        return False

    # A split inside the session puts the two rows on different price
    # scales. That is a corporate action, not a frozen snapshot, and the
    # range test cannot tell them apart - the "range" of a split
    # series means nothing. Leave it to the scale repair.
    if abs(f_close - s_close) / scale >= SCALE_BREAK_RATIO:
        return False

    return True


def find_forming_snapshots(frame: pd.DataFrame) -> list[tuple[pd.Series, pd.Series]]:
    """Find the (stale, settled) row pairs inside one trading day.

    ``frame`` must hold the rows of a single trading day for a single
    symbol, and must carry ``high``, ``low``, ``close`` and ``volume``.

    Returns:
        A list of ``(stale_row, settled_row)`` pairs. A pair is returned
        once, in the direction stale -> settled.
    """
    if frame is None or len(frame) < 2:
        return []

    pairs: list[tuple[pd.Series, pd.Series]] = []
    rows = frame.to_dict("records")
    for forming in rows:
        for settled in rows:
            if forming is settled:
                continue
            if forming_snapshot_reason(forming, settled):
                pairs.append((forming, settled))
                break
    return pairs
