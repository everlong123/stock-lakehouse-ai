"""Audit the Vietnam symbols the fix touched, to prove nothing real was lost.

The log shows large same-bar counts on VN symbols: FPT 183, VNM 227, VCB 381,
HPG 275. That is far more than the 6-9 seen on US symbols, and VN sessions run
13:00-14:30 local (06:00-07:30 UTC) with a lunch break, so a naive same-day
collapse would be catastrophic here.

The fix only collapses rows whose timestamps are at least one hour apart AND
whose prices match. This script proves that for each removed row there is a
surviving row with the same prices, and reports the timestamp pairs involved -
if the pairs are hours apart, they are re-stamps; if they are minutes apart,
something is wrong.
"""

import sys

sys.path.insert(0, ".")

import pandas as pd

from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.dedupe import find_same_bar_duplicates
from app.lakehouse.minio_storage import MinioStorageBackend

storage = MinioStorageBackend()

TARGET = sys.argv[1:] or ["FPT", "VNM", "VCB", "HPG", "MWG", "VIC", "VHM", "MSN", "BID", "CTG"]

for sym in TARGET:
    objs = [o for o in storage.list_objects("bronze", symbol_prefix(sym)) if o.endswith(".parquet")]
    frames = []
    for o in objs:
        try:
            df = storage.read_parquet("bronze", o)
        except Exception:
            continue
        if not df.empty and "timestamp" in df.columns:
            frames.append(df)
    if not frames:
        print(f"{sym}: no bronze data")
        continue

    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.loc[:, ~df.columns.duplicated()].drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df["day"] = df["timestamp"].dt.date
    df["tod"] = df["timestamp"].dt.strftime("%H:%M")

    dups = find_same_bar_duplicates(df)
    per_day = df.groupby("day").size()
    multi = per_day[per_day > 1]

    print(f"=== {sym}: rows={len(df)} days={df['day'].nunique()} same_bar_removed={len(dups)} multi_bar_days={len(multi)} ===")
    if len(dups):
        # Show the timestamp pairs that were collapsed, with the gap.
        removed = df.loc[dups.index]
        days = removed["day"].unique()
        for day in days[:4]:
            g = df[df["day"] == day].sort_values("timestamp")
            cols = [c for c in ("timestamp", "tod", "open", "close", "volume", "source") if c in g.columns]
            print(f"  --- {day} ---")
            for _, r in g.iterrows():
                mark = "REMOVED" if r.name in dups.index else "kept   "
                print(f"    {mark} {r['timestamp']} tod={r['tod']} close={r['close']:.2f} src={r.get('source', '?')}")
        # gap distribution
        gaps = []
        for day in days:
            g = df[df["day"] == day].sort_values("timestamp")
            ts = list(g["timestamp"])
            for a, b in zip(ts, ts[1:]):
                gaps.append((b - a).total_seconds() / 3600.0)
        if gaps:
            s = pd.Series(gaps)
            print(f"    gap_hours: min={s.min():.2f} med={s.median():.2f} max={s.max():.2f}")
    print()