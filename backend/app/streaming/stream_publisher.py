"""StreamPublisher - bridge Finnhub WebSocket trades into Kafka.

This module wires the :class:`FinnhubWebSocketClient` together with the
:class:`StockKafkaProducer` so that real-time ticks (grouped per-second into
OHLCV bars) end up on a Kafka topic ready for downstream consumption by the
lakehouse pipeline (see :mod:`app.streaming.kafka_consumer`).

Architecture::

    Finnhub WS ──► StreamPublisher ──► Kafka topic "stock-ohlcv-raw"
                                                 │
                                                 ▼
                                       KafkaConsumer → Bronze/Silver/Gold

Free tier specifics:
- Max 50 subscriptions per WS connection
- ~50 messages/second across all symbols
- One simultaneous WS connection

Usage::

    from app.streaming.stream_publisher import StreamPublisher

    publisher = StreamPublisher(symbols=["AAPL", "MSFT"], kafka_topic="stock-ohlcv-raw")
    publisher.start()              # non-blocking
    ...
    publisher.stop()

Or run directly::

    python -m app.streaming.stream_publisher --symbols AAPL,MSFT --interval 1s
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from app.core.config import settings
from app.core.logging_config import get_logger
from app.streaming.finnhub_websocket import (
    FinnhubWebSocketClient,
    StreamMessage,
)
from app.streaming.kafka_producer import (
    DEFAULT_BOOTSTRAP_SERVERS,
    StockKafkaProducer,
    TOPIC_OHLCV_RAW,
)

logger = get_logger(__name__)


class StreamPublisher:
    """Aggregate per-second trades from Finnhub and publish to Kafka."""

    def __init__(
        self,
        symbols: Iterable[str] | None = None,
        bootstrap_servers: str | None = None,
        topic: str = TOPIC_OHLCV_RAW,
        flush_interval_seconds: float = 1.0,
        batch_size: int = 100,
    ) -> None:
        self.symbols = [s.upper() for s in (symbols or settings.crawl_symbols.split(","))]
        self.bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers or DEFAULT_BOOTSTRAP_SERVERS
        self.topic = topic
        self.flush_interval_seconds = flush_interval_seconds
        self.batch_size = batch_size

        self._producer = StockKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        self._client: FinnhubWebSocketClient | None = None
        self._thread: threading.Thread | None = None
        self._flush_thread: threading.Thread | None = None
        self._running = False

        # Per-symbol 1-second OHLCV aggregation buffer
        self._buffers: dict[str, dict] = defaultdict(self._new_bar)
        self._buffer_lock = threading.Lock()
        self._sent_count = 0

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _new_bar() -> dict:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return {
            "symbol": "",
            "timestamp": now,
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": 0.0,
            "trades": 0,
        }

    # --------------------------------------------------------------- public

    def start(self) -> None:
        if self._running:
            logger.warning("StreamPublisher already running")
            return

        if not self._producer.bootstrap_servers:
            raise RuntimeError(
                "Kafka bootstrap servers are not configured. "
                "Set KAFKA_BOOTSTRAP_SERVERS in .env."
            )

        if not settings.finnhub_api_key:
            raise RuntimeError(
                "Finnhub API key is not configured. Set FINNHUB_API_KEY in .env."
            )

        self._running = True
        self._client = FinnhubWebSocketClient(
            api_key=settings.finnhub_api_key,
            symbols=self.symbols,
            on_message=self._handle_message,
        )
        self._client.connect(blocking=False)

        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="stream-publisher-flush"
        )
        self._flush_thread.start()

        logger.info(
            "StreamPublisher started: symbols=%d topic=%s broker=%s",
            len(self.symbols),
            self.topic,
            self.bootstrap_servers,
        )

    def stop(self) -> None:
        self._running = False
        if self._client is not None:
            self._client.stop()
            self._client = None
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=5)
            self._flush_thread = None
        # Flush any remaining buffered bars synchronously
        self._flush_buffers(force=True)
        self._producer.close()
        logger.info("StreamPublisher stopped (published=%d bars)", self._sent_count)

    def published_count(self) -> int:
        return self._sent_count

    # ------------------------------------------------------------ internals

    def _handle_message(self, message: StreamMessage) -> None:
        """Receive a single StreamMessage from the WebSocket client."""

        if message.type != "trade":
            return  # news / ping / error payloads are ignored by the publisher

        data = message.payload.get("data") or []
        if not data:
            return

        with self._buffer_lock:
            for trade in data:
                symbol = (trade.get("s") or "").upper()
                price = trade.get("p")
                volume = trade.get("v", 0)
                ts_ms = trade.get("t")
                if not symbol or price is None:
                    continue
                try:
                    ts = (
                        datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                        if ts_ms
                        else datetime.now(timezone.utc)
                    )
                except Exception:
                    ts = datetime.now(timezone.utc)

                bar = self._buffers[symbol]
                if not bar["symbol"]:
                    bar["symbol"] = symbol
                    bar["timestamp"] = ts
                    bar["open"] = float(price)
                    bar["close"] = float(price)
                # Reset bar if we have crossed into a new second
                if bar["timestamp"].replace(microsecond=0) != ts.replace(microsecond=0):
                    self._emit_bar(symbol, bar)
                    self._buffers[symbol] = self._new_bar()
                    bar = self._buffers[symbol]
                    bar["symbol"] = symbol
                    bar["timestamp"] = ts.replace(microsecond=0)
                    bar["open"] = float(price)
                    bar["close"] = float(price)

                if bar["open"] is None or float(price) < bar["low"] or bar["low"] is None:
                    bar["low"] = float(price)
                if bar["high"] is None or float(price) > bar["high"] or bar["high"] is None:
                    bar["high"] = float(price)
                bar["close"] = float(price)
                bar["volume"] += float(volume or 0)
                bar["trades"] += 1

    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(self.flush_interval_seconds)
            try:
                self._flush_buffers(force=False)
            except Exception as exc:  # noqa: BLE001
                logger.error("StreamPublisher flush error: %s", exc)

    def _flush_buffers(self, force: bool) -> None:
        with self._buffer_lock:
            bars = []
            now = datetime.now(timezone.utc)
            for symbol, bar in list(self._buffers.items()):
                age = (now - bar["timestamp"]).total_seconds() if bar.get("timestamp") else 0
                if force or age >= self.flush_interval_seconds:
                    if bar.get("open") is not None:
                        bars.append(bar)
                    self._buffers[symbol] = self._new_bar()

        if not bars:
            return

        frame = pd.DataFrame(
            [
                {
                    "symbol": bar["symbol"],
                    "timestamp": bar["timestamp"],
                    "open": bar["open"] or 0,
                    "high": bar["high"] or 0,
                    "low": bar["low"] or 0,
                    "close": bar["close"] or 0,
                    "adj_close": bar["close"] or 0,
                    "volume": bar["volume"],
                    "source": "finnhub_ws",
                    "ingestion_time": datetime.now(timezone.utc),
                }
                for bar in bars
            ]
        )
        sent = self._producer.send_ohlcv_stream(frame["symbol"].iloc[0], frame, topic=self.topic) \
            if len(frame) == 1 else self._producer.send_ohlcv_stream("batch", frame, topic=self.topic)
        self._sent_count += sent

    def _emit_bar(self, symbol: str, bar: dict) -> None:
        """Push a single (out-of-window) bar to Kafka immediately."""

        if bar.get("open") is None:
            return
        payload = pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "timestamp": bar["timestamp"],
                    "open": bar["open"],
                    "high": bar["high"],
                    "low": bar["low"],
                    "close": bar["close"],
                    "adj_close": bar["close"],
                    "volume": bar["volume"],
                    "source": "finnhub_ws",
                    "ingestion_time": datetime.now(timezone.utc),
                }
            ]
        )
        try:
            sent = self._producer.send_ohlcv_stream(symbol, payload, topic=self.topic)
            self._sent_count += sent
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to publish %s bar: %s", symbol, exc)


def parse_args():  # pragma: no cover - CLI helper
    import argparse

    parser = argparse.ArgumentParser(description="Stream Finnhub WebSocket → Kafka")
    parser.add_argument("--symbols", default=None, help="Comma-separated tickers")
    parser.add_argument("--topic", default=TOPIC_OHLCV_RAW)
    parser.add_argument(
        "--bootstrap",
        default=settings.kafka_bootstrap_servers or DEFAULT_BOOTSTRAP_SERVERS,
    )
    parser.add_argument("--interval", type=float, default=1.0, help="Flush interval (s)")
    parser.add_argument(
        "--duration", type=int, default=0,
        help="Stop after N seconds (0 = run forever). Useful for smoke tests.",
    )
    return parser.parse_args()


def _main():  # pragma: no cover - CLI helper
    args = parse_args()
    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    publisher = StreamPublisher(
        symbols=symbols,
        bootstrap_servers=args.bootstrap,
        topic=args.topic,
        flush_interval_seconds=args.interval,
    )
    publisher.start()
    try:
        if args.duration > 0:
            time.sleep(args.duration)
            publisher.stop()
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        publisher.stop()


if __name__ == "__main__":  # pragma: no cover
    _main()