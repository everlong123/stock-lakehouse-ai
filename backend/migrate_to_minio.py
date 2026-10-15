"""Migrate local lakehouse data → MinIO buckets.

Source layout (LocalStorageBackend):
  backend/data/bronze/symbol=<SYM>/year=YYYY/month=MM/<file>.parquet
  backend/data/silver/symbol=<SYM>/...
  backend/data/gold/symbol=<SYM>/...
  backend/data/models/...
  backend/data/backtests/...

Destination:
  MinIO bucket `stock-bronze`/<key>     (key = "symbol=AAPL/year=2026/..." kept as-is)
  MinIO bucket `stock-silver`/<key>
  MinIO bucket `stock-gold`/<key>
  MinIO bucket `stock-models`/<key>
  MinIO bucket `stock-backtests`/<key>

Idempotent: skips objects already present in MinIO (by size match).
"""
from __future__ import annotations

import sys
from pathlib import Path

from minio import Minio

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

LAYER_TO_BUCKET = {
    "bronze": "stock-bronze",
    "silver": "stock-silver",
    "gold": "stock-gold",
    "models": "stock-models",
    "backtests": "stock-backtests",
}


def migrate(client: Minio, src_dir: Path, bucket: str, layer: str) -> tuple[int, int]:
    if not src_dir.exists():
        print(f"  [{layer}] {src_dir} not found, skip")
        return 0, 0

    uploaded = 0
    skipped = 0
    total_files = sum(1 for _ in src_dir.rglob("*.parquet"))
    print(f"  [{layer}] found {total_files} parquet files")

    for path in src_dir.rglob("*.parquet"):
        rel = path.relative_to(src_dir).as_posix()
        # Skip if same-size object already in MinIO
        try:
            existing = client.stat_object(bucket, rel)
            if existing.size == path.stat().st_size:
                skipped += 1
                continue
        except Exception:
            pass

        client.fput_object(bucket, rel, str(path))
        uploaded += 1
        if uploaded % 50 == 0:
            print(f"  [{layer}] uploaded {uploaded}...")

    return uploaded, skipped


def main() -> int:
    print("== Migrate local → MinIO ==")
    client = Minio(
        "127.0.0.1:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False,
    )

    for layer, bucket in LAYER_TO_BUCKET.items():
        src = DATA / layer
        if not src.exists():
            print(f"  [{layer}] not present, skip")
            continue
        up, sk = migrate(client, src, bucket, layer)
        print(f"  [{layer}] uploaded={up} skipped={sk}")

    print("== Done ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
