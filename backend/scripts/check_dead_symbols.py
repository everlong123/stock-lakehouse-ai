"""Check whether the dead tickers still have rows in the lake, and how fresh.

A ticker that Yahoo no longer serves will 404 on every refresh, so the lake
keeps its last good rows and goes stale. This reports the watermark per
symbol so the two groups can be told apart: symbols with no rows at all were
never ingested, symbols with rows are simply no longer updating.

Run inside the backend container:

    docker exec stock-lakehouse-backend python scripts/check_dead_symbols.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.minio_storage import MinioStorageBackend

DEAD = [
    "BK", "BLUE", "CCRN", "CHK", "CMA", "CPRX", "CTRA", "DAWN", "DENN",
    "EXPR", "FOLD", "HOLX", "IPG", "KLG", "LTHM", "PEAK", "PGRE", "PLL",
    "TCO", "TGNA", "WBA", "WBD",
]


def main() -> None:
    st = MinioStorageBackend()

    for sym in DEAD:
        try:
            sym_keys = [k for k in st.list_objects("bronze", f"symbol={sym}/")
                        if k.endswith(".parquet")]
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym:8s} LIST FAILED ({type(exc).__name__})")
            continue

        if not sym_keys:
            print(f"  {sym:8s} NO ROWS in bronze")
            continue

        rows = 0
        latest = None
        for k in sym_keys:
            try:
                df = st.read_parquet("bronze", k)
            except Exception:  # noqa: BLE001
                continue
            if df is None or df.empty or "timestamp" not in df.columns:
                continue
            rows += len(df)
            ts = pd.to_datetime(df["timestamp"], errors="coerce", utc=True).max()
            if pd.notna(ts) and (latest is None or ts > latest):
                latest = ts
        print(f"  {sym:8s} rows={rows:6d}  latest={latest}")


if __name__ == "__main__":
    main()
