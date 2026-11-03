"""Report the latest trade date present in each lakehouse layer.

Run inside the backend container:

    docker exec stock-lakehouse-backend python scripts/check_latest_date.py
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.minio_storage import MinioStorageBackend

LAYERS = ("bronze", "silver", "gold")


def main() -> None:
    st = MinioStorageBackend()
    for layer in LAYERS:
        keys = list(st.list_objects(layer))
        syms = set()
        month_buckets = collections.defaultdict(set)
        for k in keys:
            if "_errors/" in k or k.startswith("_errors/"):
                continue
            parts = dict(p.split("=", 1) for p in k.split("/") if "=" in p)
            sym = parts.get("symbol", "").upper()
            if not sym:
                continue
            syms.add(sym)
            year, month = parts.get("year"), parts.get("month")
            if year and month:
                month_buckets[sym].add(f"{year}-{month}")

        print(f"--- {layer}: {len(syms)} symbols, {len(keys)} objects")
        if not syms:
            continue
        all_months = sorted({m for v in month_buckets.values() for m in v})
        if all_months:
            counts = collections.Counter(
                m for v in month_buckets.values() for m in v
            )
            latest = all_months[-1]
            latest_n = counts[latest]
            print(f"    month buckets: {all_months[0]} .. {latest} ({len(all_months)} total)")
            print(f"    latest bucket {latest}: {latest_n}/{len(syms)} symbols")
            print(f"    bucket histogram (last 6): "
                  + ", ".join(f"{m}={counts[m]}" for m in all_months[-6:]))


if __name__ == "__main__":
    main()
