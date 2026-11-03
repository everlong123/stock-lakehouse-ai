"""Find the exact origin of the 1970 timestamps and the /1000 prices.

AAPL is a US symbol, yet it carries 814 rows stamped 1970 with prices like
57.0. The vn_ws publisher only subscribes to VN tickers, so those rows cannot
have come from it directly. Something writes US symbols with VN-shaped data.

This dumps the raw parquet bytes' metadata for the affected partitions and
inspects the rows in full: symbol, source, ingestion_time, prices. The
ingestion_time is the key - it identifies WHICH run wrote them.
"""

import sys

sys.path.insert(0, ".")

import pandas as pd

from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend

storage = MinioStorageBackend()

EPOCH_CUTOFF = pd.Timestamp("2020-01-01", tz="UTC")

for sym in ["AAPL", "MSFT"]:
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
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["ingestion_time"] = pd.to_datetime(df["ingestion_time"], utc=True, errors="coerce")
    df = df.loc[:, ~df.columns.duplicated()]

    bad = df[df["timestamp"] < EPOCH_CUTOFF]
    print(f"=== {sym}: rows={len(df)} bad_rows={len(bad)} ===")
    if bad.empty:
        print()
        continue

    print("source breakdown of bad rows:")
    print(bad["source"].value_counts().to_string())
    print()
    print("symbol breakdown of bad rows:")
    print(bad["symbol"].value_counts().head(10).to_string())
    print()
    print("ingestion_time range of bad rows:")
    print(f"  min={bad['ingestion_time'].min()}  max={bad['ingestion_time'].max()}")
    print()
    print("sample bad rows:")
    cols = [c for c in ("symbol", "timestamp", "open", "high", "low", "close", "adj_close", "volume", "source", "ingestion_time") if c in bad.columns]
    print(bad[cols].head(12).to_string(index=False))
    print()
    print("partition paths containing bad rows:")
    print(bad["_partition"].value_counts().head(5).to_string() if "_partition" in bad.columns else "(no partition col)")
    print()

    # Which partitions hold them?
    print("--- per-object bad counts ---")
    for o in objs:
        try:
            d = storage.read_parquet("bronze", o)
        except Exception:
            continue
        if d.empty or "timestamp" not in d.columns:
            continue
        ts = pd.to_datetime(d["timestamp"], utc=True, errors="coerce")
        n = int((ts < EPOCH_CUTOFF).sum())
        if n:
            print(f"  {o}: {n}/{len(d)} bad  (object size {storage.client.stat_object(storage._bucket('bronze'), o).size} bytes)")
    print()