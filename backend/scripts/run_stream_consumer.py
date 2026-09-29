"""Run the Kafka consumer pipeline standalone.

This script subscribes to ``stock-ohlcv-raw`` (the topic fed by
:class:`app.streaming.StreamPublisher`) and writes every message through the
Bronze + Silver + Gold Medallion layers.  Run it in a dedicated process:

    python scripts/run_stream_consumer.py
    python scripts/run_stream_consumer.py --topic stock-ohlcv-raw --group-id stock-lakehouse

The same code is also importable as :class:`StreamConsumerService` for
embedding inside the FastAPI lifespan or Dagster jobs.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.logging_config import get_logger
from app.streaming.kafka_consumer import StockKafkaConsumer

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consume Kafka and write to Lakehouse")
    parser.add_argument("--topic", default="stock-ohlcv-raw")
    parser.add_argument("--group-id", default="stock-lakehouse-consumer")
    parser.add_argument("--max-records", type=int, default=0,
                        help="Stop after processing N records (0 = run forever)")
    parser.add_argument("--timeout-ms", type=int, default=5000,
                        help="Poll timeout in ms")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    consumer = StockKafkaConsumer(
        group_id=args.group_id,
        topics=[args.topic],
    )

    def _shutdown(signum, frame):
        logger.info("Received signal %s - shutting down", signum)
        consumer.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    consumer.start()
    processed = 0
    try:
        while True:
            time.sleep(0.5)
            if args.max_records and processed >= args.max_records:
                logger.info("Reached max-records (%d) - exiting", args.max_records)
                break
    finally:
        consumer.stop()


if __name__ == "__main__":
    main()