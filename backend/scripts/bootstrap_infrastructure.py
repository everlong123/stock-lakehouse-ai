"""Bootstrap MinIO buckets and Kafka topics for the Stock Lakehouse.

After ``docker compose up -d`` the infrastructure containers start, but the
Bronze/Silver/Gold buckets and the Kafka topics we use are not
automatically created.  This script:

1. Creates the MinIO buckets listed in ``.env`` (default:
   ``stock-bronze``, ``stock-silver``, ``stock-gold``, ``stock-models``,
   ``stock-backtests``).
2. Creates the Kafka topics used by the streaming pipeline
   (``stock-ohlcv-raw``, ``stock-ohlcv-enriched``, ``stock-alerts``,
   ``stock-tick``, ``stock-candle-1m``).

Run it once after the first ``docker compose up``::

    python scripts/bootstrap_infrastructure.py

It is idempotent - buckets and topics that already exist are skipped.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# Default Kafka topics to create if USE_KAFKA=true.
KAFKA_TOPICS: list[tuple[str, int]] = [
    ("stock-ohlcv-raw", 3),
    ("stock-ohlcv-enriched", 3),
    ("stock-alerts", 1),
    ("stock-tick", 3),
    ("stock-candle-1m", 3),
]


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


def bootstrap_kafka(verbose: bool = True) -> bool:
    """Create the Kafka topics used by the streaming pipeline."""

    try:
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError
    except ImportError:
        logger.error("kafka-python not installed - skipping topic bootstrap")
        return False

    bootstrap = settings.kafka_bootstrap_servers
    if not bootstrap:
        logger.error("KAFKA_BOOTSTRAP_SERVERS is not configured")
        return False

    # Wait for Kafka to become available (it can take ~30s after compose up)
    admin: KafkaAdminClient | None = None
    for attempt in range(30):
        try:
            admin = KafkaAdminClient(bootstrap_servers=bootstrap, client_id="bootstrap")
            admin.list_topics()
            break
        except Exception as exc:  # noqa: BLE001
            if verbose:
                logger.info(
                    "Waiting for Kafka at %s (attempt %d): %s",
                    bootstrap,
                    attempt + 1,
                    exc,
                )
            time.sleep(2)
            admin = None

    if admin is None:
        logger.error("Kafka not reachable at %s", bootstrap)
        return False

    topics = [
        NewTopic(name=name, num_partitions=partitions, replication_factor=1)
        for name, partitions in KAFKA_TOPICS
    ]
    try:
        admin.create_topics(new_topics=topics, validate_only=False)
        logger.info("Kafka topics created: %s", [t.name for t in topics])
    except TopicAlreadyExistsError:
        if verbose:
            logger.info("All Kafka topics already exist")
    except Exception as exc:  # noqa: BLE001
        # Partial creation may have succeeded
        logger.warning("Kafka topic bootstrap reported: %s", exc)

    created = admin.list_topics()
    logger.info("Kafka topics on %s: %s", bootstrap, sorted(t for t in created if not t.startswith("__")))
    admin.close()
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap MinIO buckets and Kafka topics.")
    parser.add_argument("--skip-minio", action="store_true")
    parser.add_argument("--skip-kafka", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not args.skip_minio:
        bootstrap_minio()
    if not args.skip_kafka:
        bootstrap_kafka()


if __name__ == "__main__":
    main()