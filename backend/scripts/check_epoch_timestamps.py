"""Investigate the 1970-01-xx dates found on the VN symbols.

The VN audit surfaced days like datetime.date(1970, 1, 10) on VCB, and
1970-01-13 on VNM, 1970-01-05 on FPT, 1970-01-27 on HPG. A 1970 date in a
price series is the classic symptom of an epoch-time integer being read as a
nanosecond timestamp, or a zero/None timestamp coerced to 1970-01-01.

This dumps those rows to see what they actually are, and counts how many rows
across the lakehouse carry a timestamp before 2020 - those are certainly
corrupt and would silently poison every rolling indicator.
"""

import sys

sys.path.insert(0, ".")

import pandas as pd

from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend

storage = MinioStorageBackend()

EPOCH_CUTOFF = pd.Timestamp("2020-01-01", tz="UTC")

for sym in sys.argv[1:] or ["VCB", "VNM", "FPT", "HPG"]:
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
        continue

    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.loc[:, ~df.columns.duplicated()].drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

    bad = df[df["timestamp"] < EPOCH_CUTOFF]
    print(f"=== {sym}: rows={len(df)} rows_before_2020={len(bad)} ===")
    if len(bad):
        cols = [c for c in ("timestamp", "open", "high", "low", "close", "volume", "source", "ingestion_time") if c in df.columns]
        print(bad[cols].head(20).to_string(index=False))
        print(f"  distinct bad timestamps: {bad['timestamp'].nunique()}")
        print(f"  bad day histogram: {bad['timestamp'].dt.date.value_counts().to_dict()}")
    print()

print("=== how widespread is the epoch problem? ===")
from app.core.constants import ALL_SYMBOLS

total_bad = 0
symbols_with_bad = []
for sym in ALL_SYMBOLS[:200]:
    try:
        objs = [o for o in storage.list_objects("bronze", symbol_prefix(sym)) if o.endswith(".parquet")]
    except Exception:
        continue
    if not objs:
        continue
    frames = []
    for o in objs:
        try:
            d = storage.read_parquet("bronze", o)
        except Exception:
            continue
        if not d.empty and "timestamp" in d.columns:
            frames.append(d[["timestamp"]])
    if not frames:
        continue
    s = pd.concat(frames, ignore_index=True)
    s["timestamp"] = pd.to_datetime(s["timestamp"], utc=True, errors="coerce")
    n_bad = int((s["timestamp"] < EPOCH_CUTOFF).sum())
    if n_bad:
        total_bad += n_bad
        symbols_with_bad.append((sym, n_bad))

print(f"symbols with pre-2020 timestamps (of 200 scanned): {len(symbols_with_bad)}")
print(f"total bad rows: {total_bad}")
for sym, n in symbols_with_bad[:20]:
    print(f"  {sym:10s} {n}")