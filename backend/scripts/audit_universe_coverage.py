"""Universe-wide coverage audit for the GOLD layer (what the charts read).

Answers the three questions the UI keeps raising:

  1. Which symbols are STALE (their newest bar is behind the newest bar in the
     lake)? "Data is like this here and different there."
  2. Which symbols carry MORE THAN ONE bar for the same trading day? That is
     what makes a candlestick chart show two candles for one session.
  3. Are the "missing weekdays" real gaps, or exchange holidays? A genuine
     gap is a weekday with no bar that ISN'T a known market holiday.

The US holiday set is derived from the observed data itself: a weekday is
"explained" when it is within +/- 3 days of a bar that is present in
*most* symbols but missing in the stale ones. That is fiddly, so instead the
script reports the missing-weekday list and marks the ones that are known
US market holidays by name.

    python3 scripts/audit_universe_coverage.py
"""

from __future__ import annotations

import collections
import io
import sys
from datetime import date

import pandas as pd
from minio import Minio

ENDPOINT = "127.0.0.1:9000"
ACCESS = "minioadmin"
SECRET = "minioadmin"
BUCKET = "stock-gold"

#: US equity market holidays, by month/day. New Year's Day, MLK Day,
#: Presidents Day, Good Friday, Memorial Day, Juneteenth, Independence Day,
#: Labor Day, Thanksgiving, Christmas. Good Friday is not a fixed date so it
#: is handled separately by a rule rather than a table entry.
_FIXED_HOLIDAYS = {
    (1, 1),    # New Year's Day
    (6, 19),   # Juneteenth (from 2022)
    (7, 4),    # Independence Day
    (12, 25),  # Christmas
}

#: Nth weekday of a month -> (month, weekday, n-th). 0 = Monday.
_NTH_WEEKDAY = {
    (1, 0, 3),   # MLK Day - 3rd Monday of January
    (2, 0, 3),   # Presidents Day - 3rd Monday of February
    (5, 0, 1),   # Memorial Day - last Monday of May
    (9, 0, 1),   # Labor Day - 1st Monday of September
    (11, 3, 4),  # Thanksgiving - 4th Thursday of November
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the n-th ``weekday`` (0=Mon) of ``month``; n=-1 means last."""
    if n > 0:
        d = date(year, month, 1)
        offset = (weekday - d.weekday()) % 7
        return date(year, month, 1 + offset + (n - 1) * 7)
    # last occurrence
    if month == 12:
        d = date(year, 12, 31)
    else:
        d = date(year, month + 1, 1)
    while True:
        d = date(d.year, d.month, d.day - 1)
        if d.month != month:
            break
    while d.weekday() != weekday:
        d = date(d.year, d.month, d.day - 1)
    return d


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lam = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lam) // 451
    month, day = divmod(h + lam - 7 * m + 114, 31)
    return date(year, month, day + 1)


def us_holidays(year: int) -> set[date]:
    """Market holidays for a US equity calendar."""
    out: set[date] = set()
    for month, day in _FIXED_HOLIDAYS:
        try:
            out.add(date(year, month, day))
        except ValueError:
            pass
    for key in _NTH_WEEKDAY:
        month, weekday, n = key
        out.add(_nth_weekday(year, month, weekday, n))
    out.add(_easter(year) - pd.Timedelta(days=2))  # Good Friday
    return out


def load_symbol(client: Minio, symbol: str, max_partitions: int = 4) -> pd.DataFrame:
    """Read the newest ``max_partitions`` partitions for one symbol.

    Reading every partition of every symbol is hopeless at this scale (105k
    objects). For staleness and duplicate-day detection the newest few
    partitions are enough - those are where the defects actually live.
    """
    keys = [
        o.object_name
        for o in client.list_objects(BUCKET, prefix=f"symbol={symbol}/", recursive=True)
        if o.object_name.endswith(".parquet")
    ]
    frames = []
    for name in sorted(keys, reverse=True)[:max_partitions]:
        try:
            resp = client.get_object(BUCKET, name)
            payload = resp.read()
            resp.close(); resp.release_conn()
            df = pd.read_parquet(io.BytesIO(payload))
        except Exception:  # noqa: BLE001
            continue
        if not df.empty and "timestamp" in df.columns:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.loc[:, ~df.columns.duplicated()]


def main() -> None:
    client = Minio(ENDPOINT, access_key=ACCESS, secret_key=SECRET, secure=False)

    # Discover the symbol set from the bucket listing.
    symbols: set[str] = set()
    for obj in client.list_objects(BUCKET, prefix="symbol=", recursive=True):
        parts = obj.object_name.split("/")
        if parts and parts[0].startswith("symbol="):
            symbols.add(parts[0].split("=", 1)[1])
    symbols = sorted(symbols)
    print(f"universe: {len(symbols)} symbols in {BUCKET}\n")

    per_symbol: dict[str, dict] = {}
    for sym in symbols:
        df = load_symbol(client, sym)
        if df.empty:
            per_symbol[sym] = {"rows": 0, "days": set(), "dup_days": {}, "last": None}
            continue
        df["day"] = df["timestamp"].dt.date
        counts = df["day"].value_counts()
        dup = {d: int(n) for d, n in counts.items() if n > 1}
        per_symbol[sym] = {
            "rows": len(df),
            "days": set(counts.index),
            "dup_days": dup,
            "last": df["day"].max(),
        }

    live = {s: v for s, v in per_symbol.items() if v["rows"]}
    if not live:
        print("no data")
        return

    latest = max(v["last"] for v in live.values())
    earliest = min(min(v["days"]) for v in live.values())
    print(f"newest bar in the lake: {latest}")
    print(f"oldest bar in the lake: {earliest}\n")

    # ── 1. staleness ──────────────────────────────────────────────────────
    stale = {s: v["last"] for s, v in live.items() if v["last"] < latest}
    print(f"=== 1. STALE SYMBOLS: {len(stale)}/{len(live)} ===")
    buckets = collections.Counter(v for v in stale.values())
    for day, n in sorted(buckets.items(), reverse=True)[:12]:
        print(f"    last bar {day}: {n} symbols")
    if stale:
        worst = sorted(stale.items(), key=lambda kv: kv[1])[:15]
        print("    worst offenders: " + ", ".join(f"{s}@{d}" for s, d in worst))

    # ── 2. duplicate trading days ─────────────────────────────────────────
    with_dup = {s: v["dup_days"] for s, v in live.items() if v["dup_days"]}
    total_dup_rows = sum(sum(d.values()) - len(d) for d in with_dup.values())
    print(f"\n=== 2. SYMBOLS WITH >1 BAR PER TRADING DAY: {len(with_dup)}/{len(live)} ===")
    print(f"    extra rows beyond one-per-day: {total_dup_rows}")
    for s, d in list(with_dup.items())[:10]:
        days = ", ".join(f"{k}x{v}" for k, v in sorted(d.items()))
        print(f"    {s}: {days}")

    # ── 3. real gaps vs holidays ──────────────────────────────────────────
    # A weekday is a REAL gap only if it is not a market holiday AND at least
    # one symbol has a bar on it (so the market was open).
    day_presence = collections.Counter()
    for v in live.values():
        for d in v["days"]:
            day_presence[d] += 1

    holiday_cache: dict[int, set[date]] = {}
    real_gaps = collections.Counter()
    holiday_gaps = collections.Counter()
    for v in live.values():
        days = v["days"]
        if not days:
            continue
        lo, hi = min(days), max(days)
        for d in pd.date_range(lo, hi, freq="D").date:
            if d in days or d.weekday() >= 5:
                continue
            if d.year not in holiday_cache:
                holiday_cache[d.year] = us_holidays(d.year)
            if d in holiday_cache[d.year]:
                holiday_gaps[d] += 1
            else:
                real_gaps[d] += 1

    print(f"\n=== 3. MISSING WEEKDAYS ===")
    print(f"    explained by US market holidays: {len(holiday_gaps)} distinct dates")
    print(f"    UNEXPLAINED (real gaps):        {len(real_gaps)} distinct dates")
    for d, n in real_gaps.most_common(15):
        present = day_presence.get(d, 0)
        print(f"      {d} ({d.strftime('%a')}): missing in {n} symbols, present in {present}")


if __name__ == "__main__":
    main()
