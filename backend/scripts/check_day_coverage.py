"""Per-trade-day coverage across the whole universe, plus a look at the
1970-01 bucket that shows up in the partition listing.

Run inside the backend container:

    docker exec stock-lakehouse-backend python scripts/check_day_coverage.py
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.minio_storage import MinioStorageBackend

DATE_CANDIDATES = ("date", "trade_date", "datetime", "timestamp", "time")


def pick_date_col(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if c.lower() in DATE_CANDIDATES:
            return c
    return None


def main() -> None:
    st = MinioStorageBackend()

    for layer in ("bronze", "silver", "gold"):
        keys = [k for k in st.list_objects(layer)
                if "_errors/" not in k and not k.startswith("_errors/")]

        buckets = collections.defaultdict(list)
        for k in keys:
            parts = dict(p.split("=", 1) for p in k.split("/") if "=" in p)
            sym = parts.get("symbol", "").upper()
            y, m = parts.get("year"), parts.get("month")
            if sym and y and m:
                buckets[f"{y}-{m}"].append((sym, k))

        print(f"===== {layer}: {len(buckets)} month buckets =====")

        # The suspicious early buckets: list their symbols and one row.
        for b in sorted(buckets):
            if b < "1990-01":
                syms = sorted({s for s, _ in buckets[b]})
                print(f"  OLD BUCKET {b}: {len(buckets[b])} objects, "
                      f"{len(syms)} symbols -> {syms[:8]}")
                try:
                    sym0, key0 = buckets[b][0]
                    df0 = st.read_parquet(layer, key0)
                    col = pick_date_col(df0)
                    print(f"    sample {sym0} cols={list(df0.columns)[:8]}")
                    if col:
                        s = pd.to_datetime(df0[col], errors="coerce")
                        print(f"    date range: {s.min()} .. {s.max()}")
                except Exception as exc:  # noqa: BLE001
                    print(f"    sample read failed: {exc}")

        # Day-level coverage from the newest partition.
        newest = sorted(buckets)[-1]
        per_day = collections.defaultdict(set)
        sym_days = collections.defaultdict(set)
        obj = buckets[newest]
        for sym, key in obj:
            try:
                df = st.read_parquet(layer, key)
            except Exception:  # noqa: BLE001
                continue
            col = pick_date_col(df)
            if col is None:
                continue
            s = pd.to_datetime(df[col], errors="coerce")
            for d in s.dropna().dt.date:
                per_day[d].add(sym)
                sym_days[sym].add(d)

        if per_day:
            print(f"  newest partition {newest}: {len(obj)} objects, "
                  f"{len(sym_days)} symbols")
            days = sorted(per_day)
            print(f"  trade days present: {days[0]} .. {days[-1]} "
                  f"({len(days)} distinct)")
            for d in days[-10:]:
                print(f"    {d}: {len(per_day[d])} symbols")
            allsyms = set(sym_days)
            latest = days[-1]
            print(f"  symbols whose newest row == {latest}: "
                  f"{sum(1 for v in sym_days.values() if max(v) == latest)}"
                  f"/{len(allsyms)}")
            stale = [s for s, v in sym_days.items() if max(v) < latest]
            print(f"  symbols NOT at latest day: {len(stale)} -> {sorted(stale)[:12]}")
        print()


if __name__ == "__main__":
    main()
