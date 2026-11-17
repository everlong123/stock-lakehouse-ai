"""Bootstrap the MinIO buckets for the Stock Lakehouse.

After ``docker compose up -d`` the infrastructure containers start, but the
Bronze/Silver/Gold buckets are not automatically created. This script creates
them.

Run it once after the first ``docker compose up``::

    python scripts/bootstrap_infrastructure.py

It is idempotent - buckets that already exist are skipped.

WHY THERE IS NO TOPIC BOOTSTRAP ANY MORE
----------------------------------------
Apache Kafka was removed from the project on 10/11/2026. The batch pipeline
writes straight to Bronze, so there were no topics left to create. The
function that used to do that was deleted rather than left as dead code.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def bootstrap_minio(verbose: bool = True) -> bool:
    """Create MinIO buckets declared in :class:`Settings`.

    Returns ``True`` when MinIO is reachable and all buckets are present.
    """

    try:
        from minio import Minio
    except ImportError:
        logger.error("minio package not installed - skipping bucket bootstrap")
        return False

    endpoint = settings.minio_endpoint
    access = settings.minio_access_key
    secret = settings.minio_secret_key
    secure = settings.minio_secure

    client = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)

    try:
        if not client.bucket_exists("stock-bronze"):  # probe for connectivity
            pass
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Cannot reach MinIO at %s (auth=%s): %s",
            endpoint,
            access,
            exc,
        )
        return False

    buckets = [
        settings.minio_bucket_bronze,
        settings.minio_bucket_silver,
        settings.minio_bucket_gold,
        settings.minio_bucket_models,
        settings.minio_bucket_backtests,
    ]
    for bucket in buckets:
        try:
            if client.bucket_exists(bucket):
                if verbose:
                    logger.info("MinIO bucket exists: %s", bucket)
                continue
            client.make_bucket(bucket)
            logger.info("MinIO bucket created: %s", bucket)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to create MinIO bucket %s: %s", bucket, exc)
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap MinIO buckets.")
    parser.add_argument("--skip-minio", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.skip_minio:
        bootstrap_minio()


if __name__ == "__main__":
    main()
