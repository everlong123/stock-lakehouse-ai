"""Report the actual latest trade date inside the newest partitions.

The month bucket is only the partition key. This reads the parquet files in the
newest bucket and reports the real max date column, so epoch/garbage rows are
visible rather than hidden behind a plausible-looking month.

Run inside the backend container:

    docker exec stock-lakehouse-backend python scripts/check_max_trade_date.py
"""

from __future__ import annotations

import collections
import io
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.minio_storage import MinioStorageBackend

LAYERS = ("bronze", "silver", "gold")
DATE_CANDIDATES = ("date", "trade_date", "datetime", "timestamp", "time")


def pick_date_col(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if c.lower() in DATE_CANDIDATES:
            return c
    return None


def main() -> None:
    st = MinioStorageBackend()

    for layer in LAYERS:
        keys = [k for k in st.list_objects(layer)
                if "_errors/" not in k and not k.startswith("_errors/")]

        buckets = collections.defaultdict(list)
        for k in keys:
            parts = dict(p.split("=", 1) for p in k.split("/") if "=" in p)
            sym = parts.get("symbol", "").upper()
            y, m = parts.get("year"), parts.get("month")
            if sym and y and m:
                buckets[f"{y}-{m}"].append(k)

        if not buckets:
            print(f"--- {layer}: no partitions")
            continue

        newest = sorted(buckets)[-1]
        print(f"--- {layer}: newest partition {newest} "
              f"({len(buckets[newest])} objects)")

        # Sample objects spread across the partition, not just the first one.
        sample = buckets[newest][:: max(1, len(buckets[newest]) // 12)][:12]

        per_symbol_max = {}
        bad_epoch = 0
        total_rows = 0
        max_val = None

        for key in sample:
            try:
                df = st.read_parquet(layer, key)
            except Exception as exc:  # noqa: BLE001
                print(f"    read failed {key}: {exc}")
                continue
            total_rows += len(df)
            col = pick_date_col(df)
            if col is None:
                continue
            s = pd.to_datetime(df[col], errors="coerce", utc=False)
            if s.notna().any():
                sym = key.split("/", 1)[0].split("=", 1)[1].upper()
                mx = s.max()
                per_symbol_max[sym] = mx
                if max_val is None or mx > max_val:
                    max_val = mx
            # 1970 epoch rows indicate a bad timestamp cast upstream.
            bad_epoch += int((s.dt.year == 1970).sum())

        if per_symbol_max:
            m = max(per_symbol_max.values())
            mn = min(per_symbol_max.values())
            print(f"    sampled {len(sample)} objects / {total_rows} rows")
            print(f"    max trade date = {m}")
            print(f"    min trade date = {mn}")
            print(f"    epoch(1970) rows in sample = {bad_epoch}")
            latest_count = sum(1 for v in per_symbol_max.values() if v == m)
            print(f"    symbols at max date: {latest_count}/{len(per_symbol_max)}")
        else:
            print("    no parsable date column found")


if __name__ == "__main__":
    main()
