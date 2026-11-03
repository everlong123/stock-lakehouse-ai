"""List every partition that belongs to the epoch-1970 symbols, across all layers.

The purge script only targets Bronze, but Silver and Gold were derived from the
same corrupt rows, so they carry the same 1970 buckets. This shows exactly
which partitions hold the bad data and whether each symbol also has legitimate
recent partitions (if it does not, deleting the 1970 partition would delete
the symbol's entire history).

Run inside the backend container:

    docker exec stock-lakehouse-backend python scripts/check_epoch_symbols.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.minio_storage import MinioStorageBackend

EPOCH_SYMBOLS = [
    "BID", "CTG", "FPT", "HPG", "MSN", "VCB", "VHM", "VIC", "VNM",
]


def main() -> None:
    st = MinioStorageBackend()

    for layer in ("bronze", "silver", "gold"):
        keys = [k for k in st.list_objects(layer)
                if "_errors/" not in k and not k.startswith("_errors/")]
        print(f"===== {layer} =====")

        for sym in EPOCH_SYMBOLS:
            sym_keys = sorted(k for k in keys if k.startswith(f"symbol={sym}/"))
            if not sym_keys:
                print(f"  {sym:6s} (no objects)")
                continue

            bad_total = 0
            good_total = 0
            detail = []
            for k in sym_keys:
                try:
                    df = st.read_parquet(layer, k)
                except Exception as exc:  # noqa: BLE001
                    detail.append(f"{k}: read failed {exc}")
                    continue
                if df.empty or "timestamp" not in df.columns:
                    continue
                ts = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
                bad = int((ts < pd.Timestamp("2000-01-01", tz="UTC")).sum())
                good = int((ts >= pd.Timestamp("2000-01-01", tz="UTC")).sum())
                bad_total += bad
                good_total += good
                if bad:
                    detail.append(f"{k}: {bad} bad / {good} good")

            flag = "EPOCH" if bad_total else "clean"
            print(f"  {sym:6s} {flag:5s} partitions={len(sym_keys):3d} "
                  f"bad_rows={bad_total:5d} good_rows={good_total:6d}")
            for d in detail[:6]:
                print(f"          {d}")
            if len(detail) > 6:
                print(f"          ... and {len(detail) - 6} more")
        print()


if __name__ == "__main__":
    main()
