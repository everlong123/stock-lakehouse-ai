"""CRITICAL: does the one-hour gap rule still destroy real intraday ticks?

The fix collapses two rows when they share a day, have matching prices, AND
are at least one hour apart. That rule was derived from US EOD bars, where a
re-stamp is 6.5-9.5 hours from the original.

But Vietnam symbols are fed by vn_rest at ONE-MINUTE spacing across a 4-hour
session, and VN prices are quantised to hundreds of VND (56300, 56400, ...).
Two ticks an hour apart can therefore carry byte-identical open/high/low/close
while being two genuine observations.

This checks the collision directly: within the intraday rows, how many pairs
are >= 1 hour apart AND have identical OHLC? Every such pair is a real tick
the current rule would delete.
"""

import sys

sys.path.insert(0, ".")

import pandas as pd

from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend

storage = MinioStorageBackend()
MIN_GAP_H = 1.0

for sym in sys.argv[1:] or ["VCB", "VNM", "FPT", "HPG", "MWG"]:
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
        print(f"{sym}: no data\n")
        continue

    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.loc[:, ~df.columns.duplicated()].drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df["day"] = df["timestamp"].dt.date
    df["tod"] = df["timestamp"].dt.strftime("%H:%M")

    modal = df["tod"].value_counts().index[0]
    intraday = df[df["tod"] != modal].copy()

    collisions = 0
    examples = []
    for day, g in intraday.groupby("day"):
        g = g.sort_values("timestamp")
        rows = g.to_dict("records")
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                gap_h = (b["timestamp"] - a["timestamp"]).total_seconds() / 3600.0
                if gap_h < MIN_GAP_H:
                    continue
                if all(
                    pd.isna(a.get(c)) and pd.isna(b.get(c))
                    or (a.get(c) is not None and b.get(c) is not None and abs(float(a[c]) - float(b[c])) <= 1e-8 * max(abs(float(b[c])), 1.0))
                    for c in ("open", "high", "low", "close")
                ):
                    collisions += 1
                    if len(examples) < 3:
                        examples.append((day, a, b, gap_h))

    print(f"=== {sym}: intraday rows={len(intraday)} days={intraday['day'].nunique()} ===")
    print(f"  pairs >= {MIN_GAP_H}h apart with IDENTICAL OHLC: {collisions}")
    if collisions:
        print("  -> these are REAL ticks the current rule would DELETE")
        for day, a, b, gap in examples:
            print(f"     {day}: {a['timestamp']} close={a['close']:.1f}  <->  {b['timestamp']} close={b['close']:.1f}  gap={gap:.2f}h")
    else:
        print("  -> safe: no intraday pair meets the collapse condition")
    print()