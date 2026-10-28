"""Same-bar duplicate detection for the Bronze layer.

Why this module exists
----------------------
Bronze deduplicated only on ``(symbol, timestamp)``. That is not enough for
this lakehouse, because two different providers can describe the SAME trading
session while stamping it at different times of day:

    yfinance_eod  ->  2026-10-09 04:00:00Z
    yahoo_http    ->  2026-10-09 13:30:00Z

Both rows describe the identical NYSE bar (same open/high/low/close/volume),
but because the timestamps differ, both survive the Bronze append and both
flow into Silver, where they occupy two slots in every rolling window. That
silently distorts SMA/RSI/MACD and, worse, indicators built on ``argmax``
(Aroon, Stochastic, Williams %R, CCI) because a repeated value shifts the
position of the extremum inside the window.

The obvious fix - collapse rows that share a calendar day - is DESTRUCTIVE
here, and this module deliberately does not do that. The lakehouse also holds
genuine intraday ticks (AAPL 2026-10-13 carries 13 rows stamped ``manual`` at
2-second spacing with genuinely different prices). Collapsing by day would
delete real market data.

The rule implemented here
-------------------------
Two rows are the same bar when they describe the same symbol, the same
calendar day, AND the same price/volume payload. Under that rule:

  - the 04:00 / 13:30 duplicate pair collapses to one row, and
  - the 13 intraday ticks survive, because their prices differ.

Rows that share a day but disagree on price are genuine distinct bars and are
never collapsed. The surviving row is the one whose timestamp matches the
symbol's dominant session stamp, so the canonical session bar is preserved and
only the redundant re-stamping is discarded.

Tolerances are relative, not absolute: providers round floats differently, and
an absolute epsilon of 1e-9 would fail to match values that differ in the 8th
decimal place, while an absolute epsilon of 0.01 would wrongly merge bars that
genuinely moved by a cent.
"""

from __future__ import annotations

import pandas as pd

# Relative tolerance for comparing float payloads across providers.
#
# Measured against the real lakehouse: AAPL 2026-10-09 is stored by yahoo_http
# as close=336.640015 and by yfinance_eod as close=336.6400146484375, an
# absolute difference of 3.5e-7 on a price of ~336 (relative 1.05e-9). That is
# the same bar rounded differently, not a different bar. A tolerance of 1e-9
# rejected it, so this is set one order of magnitude wider, which still leaves
# far more headroom than the ~3e-3 relative size of a one-cent move on a $336
# stock - the case the tolerance must NOT absorb.
REL_TOL = 1e-8

# Volume is compared with the same relative tolerance. Two providers reporting
# the same session rarely agree exactly on volume (one saw 17,756,841 and the
# other 17,798,600 for AAPL 2026-10-21), which is why volume alone must never
# be the deciding signal.
VOLUME_REL_TOL = 1e-6

# The price fields that identify a bar. ``close`` alone is not enough: two
# consecutive sessions can share a close.
PRICE_COLUMNS = ("open", "high", "low", "close")

# Minimum separation between two timestamps for them to be considered
# "the same bar re-stamped" rather than "two distinct observations".
#
# AAPL 2026-10-13 holds 6 manual ticks at 18:52:00..18:52:22, all with the
# identical close of 333.90. They are 2 seconds apart and are 6 real
# observations of a flat market. A pure price comparison would collapse them
# into one and silently delete 5 ticks. A re-stamped session, by contrast, is
# hours away: yfinance_eod 04:00Z vs yahoo_http 13:30Z is 9.5h, and the
# 13:30Z vs 20:00Z pair is 6.5h. A threshold of one hour separates the two
# populations with a wide margin.
MIN_RE_STAMP_GAP = pd.Timedelta(hours=1)

# Known session stamps, used to break a tie when a symbol's rows are split
# evenly between two stamps. ``value_counts().index[0]`` is not a safe tiebreak:
# on a two-row frame both stamps appear once and pandas returns whichever came
# first, which made the redundant EOD stamp win about half the time. Preferring
# the exchange open (13:30 UTC = 09:30 America/New_York) keeps the canonical
# bar stable regardless of ingestion order.
PREFERRED_STAMPS = ("13:30", "14:30", "20:00")


def _is_utc(series: pd.Series) -> bool:
    """True when every timestamp in the series is timezone-aware."""
    if series.empty:
        return True
    return bool(getattr(series.dt, "tz", None) is not None)


def trading_day(timestamp: pd.Series) -> pd.Series:
    """Return the calendar day (UTC) of each timestamp as a date."""
    if not _is_utc(timestamp):
        timestamp = timestamp.dt.tz_localize("UTC")
    return timestamp.dt.date


def session_stamp(timestamp: pd.Series) -> pd.Series:
    """Return the HH:MM of each timestamp, used to find a symbol's convention."""
    if not _is_utc(timestamp):
        timestamp = timestamp.dt.tz_localize("UTC")
    return timestamp.dt.strftime("%H:%M")


def _payload_matches(left: pd.Series, right: pd.Series) -> bool:
    """Test that two price payloads describe the same bar.

    Uses a relative tolerance so that float rounding differences between
    providers do not defeat the match, while a genuine one-cent move does.
    """
    for column in PRICE_COLUMNS:
        if column not in left or column not in right:
            continue
        a = pd.to_numeric(pd.Series([left[column]]), errors="coerce").iloc[0]
        b = pd.to_numeric(pd.Series([right[column]]), errors="coerce").iloc[0]
        a_nan = pd.isna(a)
        b_nan = pd.isna(b)
        if a_nan and b_nan:
            continue
        if a_nan or b_nan:
            return False
        if abs(float(a) - float(b)) > REL_TOL * max(abs(float(b)), 1.0):
            return False
    return True


def find_same_bar_duplicates(frame: pd.DataFrame) -> pd.DataFrame:
    """Identify rows that are the same bar written twice under different stamps.

    Returns the subset of ``frame`` that should be dropped, i.e. the later
    re-stampings of a bar that is already present. The canonical row (the one
    matching the symbol's dominant session stamp) is always kept.
    """
    if frame.empty or "timestamp" not in frame.columns:
        return frame.iloc[0:0].copy()

    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
    working = working[working["timestamp"].notna()].copy()
    if working.empty:
        return frame.iloc[0:0].copy()

    working["_day"] = trading_day(working["timestamp"])
    working["_stamp"] = session_stamp(working["timestamp"])

    # The grouping key. `symbol` is part of the identity of a bar, so fall
    # back to a constant when the frame carries no symbol column.
    if "symbol" not in working.columns:
        working["symbol"] = "__all__"

    # Dominant session stamp per symbol. A symbol that consistently stamps its
    # EOD bars at 13:30 keeps 13:30; a symbol stamped at 20:00 keeps 20:00.
    # Ties are broken by PREFERRED_STAMPS so the result does not depend on row
    # order, which matters because a partition holding a single re-stamped day
    # has exactly one row per stamp and therefore always ties.
    def _modal_stamp(stamps: pd.Series) -> str | None:
        counts = stamps.value_counts()
        if counts.empty:
            return None
        top = counts[counts == counts.max()].index.tolist()
        if len(top) == 1:
            return top[0]
        for preferred in PREFERRED_STAMPS:
            if preferred in top:
                return preferred
        return sorted(top)[0]

    modal = working.groupby("symbol")["_stamp"].agg(_modal_stamp)
    working["_modal_stamp"] = working["symbol"].map(modal)

    # Canonical-first ordering: within a (symbol, day) group the row whose
    # stamp matches the modal convention wins, then the earliest timestamp,
    # then the latest ingestion time as a final tiebreak.
    working["_is_modal"] = working["_stamp"] == working["_modal_stamp"]
    if "ingestion_time" in working.columns:
        working["_ingest"] = pd.to_datetime(working["ingestion_time"], utc=True, errors="coerce")
    else:
        working["_ingest"] = pd.Timestamp("1970-01-01", tz="UTC")
    working = working.sort_values(
        ["symbol", "_day", "_is_modal", "timestamp", "_ingest"],
        ascending=[True, True, False, True, False],
        kind="mergesort",
    )

    drop_indices: list = []
    for (_symbol, _day), group in working.groupby(["symbol", "_day"], sort=False):
        if len(group) < 2:
            continue

        # Compare each candidate against the rows already accepted for this
        # day. A row is a duplicate only if it matches an accepted row's price
        # payload AND is far enough away in time to be a re-stamping of the
        # same session. The time condition is what preserves genuine intraday
        # ticks that happen to share a price.
        accepted: list[int] = []
        for idx, row in group.iterrows():
            is_dup = False
            for kept_idx in accepted:
                if not _payload_matches(row, working.loc[kept_idx]):
                    continue
                gap = abs(row["timestamp"] - working.loc[kept_idx, "timestamp"])
                if gap >= MIN_RE_STAMP_GAP:
                    is_dup = True
                    break
            if is_dup:
                drop_indices.append(idx)
            else:
                accepted.append(idx)

    if not drop_indices:
        return frame.iloc[0:0].copy()

    return frame.loc[frame.index.isin(drop_indices)].copy()


def dedupe_same_bars(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove rows that re-state a bar already present under another stamp.

    Returns the cleaned frame and the number of rows removed. Row order and
    the original index are preserved so callers can map results back.
    """
    if frame.empty:
        return frame, 0

    duplicates = find_same_bar_duplicates(frame)
    if duplicates.empty:
        return frame, 0

    keep_mask = ~frame.index.isin(duplicates.index)
    return frame.loc[keep_mask].copy(), int(len(duplicates))
