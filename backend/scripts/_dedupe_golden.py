"""Golden test: the vectorised dedupe must match the original per-row version.

The original implementation compared rows with `group.iterrows()` and
`working.loc[kept_idx]`, using `_payload_matches` on pandas Series. The new
one works on plain float tuples.

This script re-implements the ORIGINAL algorithm exactly and compares the set
of dropped rows, over a variety of frames - including the tricky ones:
re-stamped sessions, genuine intraday ticks that share a price, NaN prices,
and multi-symbol frames.
"""
import sys
sys.path.insert(0, ".")
import numpy as np
import pandas as pd

from app.lakehouse.dedupe import (
    MIN_RE_STAMP_GAP,
    PRICE_COLUMNS,
    REL_TOL,
    find_same_bar_duplicates,
    PREFERRED_STAMPS,
    session_stamp,
    trading_day,
)


def _payload_matches(left, right):
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


def original_find_same_bar_duplicates(frame):
    if frame.empty or "timestamp" not in frame.columns:
        return frame.iloc[0:0].copy()
    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
    working = working[working["timestamp"].notna()].copy()
    if working.empty:
        return frame.iloc[0:0].copy()
    working["_day"] = trading_day(working["timestamp"])
    working["_stamp"] = session_stamp(working["timestamp"])
    if "symbol" not in working.columns:
        working["symbol"] = "__all__"

    def _modal_stamp(stamps):
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

    drop_indices = []
    for (_symbol, _day), group in working.groupby(["symbol", "_day"], sort=False):
        if len(group) < 2:
            continue
        accepted = []
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


def make(rows):
    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame


CASES = {}

# 1. Classic re-stamped session (04:00 vs 13:30) - the real-world case.
CASES["re-stamped session"] = make([
    {"symbol": "AAPL", "timestamp": "2026-10-09 04:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
    {"symbol": "AAPL", "timestamp": "2026-10-09 13:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
])

# 2. Genuine intraday ticks 2 seconds apart with an IDENTICAL close.
#    The 1-hour separation rule must keep ALL of them.
ticks = []
for i in range(6):
    ticks.append({
        "symbol": "AAPL", "timestamp": f"2026-10-13 18:52:{i * 2:02d}Z",
        "open": 333.90, "high": 333.90, "low": 333.90, "close": 333.90,
    })
CASES["intraday ticks (same price)"] = make(ticks)

# 3. Mixed: re-stamped session + intraday ticks + a distinct bar.
CASES["mixed"] = make([
    {"symbol": "AAPL", "timestamp": "2026-10-09 04:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
    {"symbol": "AAPL", "timestamp": "2026-10-09 13:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
    {"symbol": "AAPL", "timestamp": "2026-10-13 18:52:00Z", "open": 333.90, "high": 333.90, "low": 333.90, "close": 333.90},
    {"symbol": "AAPL", "timestamp": "2026-10-13 18:52:22Z", "open": 333.90, "high": 333.90, "low": 333.90, "close": 333.90},
    {"symbol": "AAPL", "timestamp": "2026-10-14 13:30:00Z", "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5},
])

# 4. Same day, DIFFERENT prices -> two genuine bars, neither dropped.
CASES["different prices"] = make([
    {"symbol": "AAPL", "timestamp": "2026-10-09 04:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
    {"symbol": "AAPL", "timestamp": "2026-10-09 13:30:00Z", "open": 100.1, "high": 101.1, "low": 99.1, "close": 100.6},
])

# 5. NaN prices.
CASES["nan prices"] = make([
    {"symbol": "AAPL", "timestamp": "2026-10-09 04:00:00Z", "open": float("nan"), "high": 101.0, "low": 99.0, "close": 100.5},
    {"symbol": "AAPL", "timestamp": "2026-10-09 13:30:00Z", "open": float("nan"), "high": 101.0, "low": 99.0, "close": 100.5},
])

# 6. One NaN vs one value -> not a match.
CASES["one nan"] = make([
    {"symbol": "AAPL", "timestamp": "2026-10-09 04:00:00Z", "open": float("nan"), "high": 101.0, "low": 99.0, "close": 100.5},
    {"symbol": "AAPL", "timestamp": "2026-10-09 13:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
])

# 7. Multiple symbols, same day - must not collapse across symbols.
CASES["multi symbol"] = make([
    {"symbol": "AAPL", "timestamp": "2026-10-09 13:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
    {"symbol": "MSFT", "timestamp": "2026-10-09 13:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
    {"symbol": "MSFT", "timestamp": "2026-10-09 04:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
])

# 8. Rounding difference between providers (relative tolerance case).
CASES["rounding"] = make([
    {"symbol": "AAPL", "timestamp": "2026-10-09 04:00:00Z", "open": 336.6400146484375, "high": 340.0, "low": 330.0, "close": 336.6400146484375},
    {"symbol": "AAPL", "timestamp": "2026-10-09 13:30:00Z", "open": 336.640015, "high": 340.0, "low": 330.0, "close": 336.640015},
])

# 9. Three rows for one day: 13:30 canonical + 20:00 settled + 04:00 eod.
CASES["three stamps"] = make([
    {"symbol": "AAPL", "timestamp": "2026-10-09 13:30:00Z", "open": 349.12, "high": 352.0, "low": 348.0, "close": 350.0},
    {"symbol": "AAPL", "timestamp": "2026-10-09 20:00:00Z", "open": 349.11, "high": 352.0, "low": 348.0, "close": 350.0},
    {"symbol": "AAPL", "timestamp": "2026-10-09 04:00:00Z", "open": 349.12, "high": 352.0, "low": 348.0, "close": 350.0},
])

# 10. A frame with no symbol column.
CASES["no symbol column"] = make([
    {"timestamp": "2026-10-09 04:00:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
    {"timestamp": "2026-10-09 13:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
])

# 11. Exactly 1 hour apart - the boundary is inclusive (gap >= 1h).
CASES["exactly one hour"] = make([
    {"symbol": "AAPL", "timestamp": "2026-10-09 12:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
    {"symbol": "AAPL", "timestamp": "2026-10-09 13:30:00Z", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
])

failures = 0
for name, frame in CASES.items():
    expected = original_find_same_bar_duplicates(frame)
    actual = find_same_bar_duplicates(frame)
    exp_idx = sorted(expected.index.tolist())
    act_idx = sorted(actual.index.tolist())
    status = "OK  " if exp_idx == act_idx else "FAIL"
    if exp_idx != act_idx:
        failures += 1
    print("%s %-28s rows=%d dropped expected=%s actual=%s" % (
        status, name, len(frame), exp_idx, act_idx))

print()
print("%d cases, %d mismatches" % (len(CASES), failures))
sys.exit(1 if failures else 0)
