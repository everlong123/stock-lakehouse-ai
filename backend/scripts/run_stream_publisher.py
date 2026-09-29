"""CLI helper to start the WebSocket → Kafka publisher."""

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
from app.streaming.stream_publisher import StreamPublisher

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream Finnhub WebSocket trades into Kafka.",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated tickers. Defaults to settings.crawl_symbols.",
    )
    parser.add_argument("--topic", default="stock-ohlcv-raw")
    parser.add_argument(
        "--bootstrap",
        default=None,
        help="Kafka bootstrap servers (default: settings.kafka_bootstrap_servers).",
    )
    parser.add_argument(
        "--interval", type=float, default=1.0,
        help="Flush interval in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--duration", type=int, default=0,
        help="Stop after N seconds (0 = run until Ctrl+C).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    symbols = [item.strip() for item in args.symbols.split(",")] if args.symbols else None
    publisher = StreamPublisher(
        symbols=symbols,
        bootstrap_servers=args.bootstrap,
        topic=args.topic,
        flush_interval_seconds=args.interval,
    )

    def _shutdown(signum, frame):
        logger.info("Received signal %s - shutting down", signum)
        publisher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    publisher.start()
    try:
        if args.duration > 0:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(1)
                count = publisher.published_count()
                if count and count % 50 == 0:
                    logger.info("Published %d bars so far", count)
    finally:
        publisher.stop()


if __name__ == "__main__":
    main()