"""CLI helper to start the Vietnamese stream publisher."""

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
from app.streaming.vn_stream_publisher import VNStreamPublisher

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stream SSI iBoard real-time quotes (HOSE/HNX/UPCOM) into Kafka. "
            "Free, no API key required."
        ),
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated VN tickers. Defaults to settings.vn_ws_symbols.",
    )
    parser.add_argument(
        "--boards",
        default=None,
        help="Comma-separated board IDs (MAIN, HNX, UPCOM). Default from settings.",
    )
    parser.add_argument("--topic", default="stock-ohlcv-raw")
    parser.add_argument(
        "--bootstrap",
        default=None,
        help="Kafka bootstrap servers (default: settings.kafka_bootstrap_servers).",
    )
    parser.add_argument(
        "--interval", type=float, default=5.0,
        help="Flush interval in seconds (default: 5.0).",
    )
    parser.add_argument(
        "--duration", type=int, default=0,
        help="Stop after N seconds (0 = run until Ctrl+C).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    symbols = (
        [s.strip() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else None
    )
    boards = (
        [b.strip() for b in args.boards.split(",") if b.strip()]
        if args.boards
        else None
    )
    publisher = VNStreamPublisher(
        symbols=symbols,
        bootstrap_servers=args.bootstrap,
        topic=args.topic,
        flush_interval_seconds=args.interval,
        boards=boards,
    )

    def _shutdown(signum, _frame):
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
