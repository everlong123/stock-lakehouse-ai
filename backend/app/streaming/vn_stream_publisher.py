"""VN stream publisher - bridge SSI iBoard WebSocket ticks into Kafka.

This module mirrors :mod:`app.streaming.stream_publisher` for the
Vietnamese market. It consumes real-time quote ticks from
:class:`VNWebSocketClient`, aggregates them into 1-minute OHLCV bars
(the cadence at which SSI REST candles are available), and publishes
the result to the same Kafka topic the US publisher uses.

Architecture::

    SSI iBoard WS ──► VNStreamPublisher ──► Kafka topic "stock-ohlcv-raw"
                                                       │       (source=vn_ws)
                                                       ▼
                                          StockKafkaConsumer → Bronze/Silver

Free / no-key specifics:
- The public iBoard pushstream does not require any API key. The
  Vietnamese symbol universe is hand-picked — the publisher must NEVER
  fall back to a synthetic data source (just like its US counterpart).
- A :class:`VNRestPoller` runs alongside the WS to keep the pipeline
  producing real data when the WS is silent (weekends, off-hours).
- Bar interval is 1 minute. HOSE/HNX trade at 1-5 ticks per second, so
  sub-minute bars are too noisy; daily bars are too coarse for a
  streaming demo. 1 minute matches the native SSI candle resolution.
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
from app.streaming.kafka_producer import (
    DEFAULT_BOOTSTRAP_SERVERS,
    StockKafkaProducer,
    TOPIC_OHLCV_RAW,
)
from app.streaming.vn_rest_poller import VNRestPoller
from app.streaming.vn_websocket import (
    DEFAULT_BOARDS,
    VNQuoteTick,
    VNWebSocketClient,
    build_default_client,
)

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Per-symbol bar accumulator
# ─────────────────────────────────────────────────────────────────────────────


class _BarAccumulator:
    """Mutable 1-minute OHLCV accumulator for a single symbol."""

    __slots__ = (
        "symbol",
        "bar_ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trades",
    )

    def __init__(self, symbol: str = "", ts: datetime | None = None) -> None:
        self.symbol = symbol
        self.bar_ts: datetime | None = ts
        self.open: float | None = None
        self.high: float | None = None
        self.low: float | None = None
        self.close: float | None = None
        self.volume: float = 0.0
        self.trades: int = 0

    def update(self, tick: VNQuoteTick) -> None:
        """Fold a single tick into the bar (O(1))."""

        price = float(tick.price or 0.0)
        if price <= 0:
            return
        volume = float(tick.volume or 0.0)
        if self.open is None:
            self.open = price
            self.high = price
            self.low = price
        else:
            if price > self.high:
                self.high = price
            if price < self.low:
                self.low = price
        self.close = price
        self.volume += volume
        self.trades += 1

    def is_complete(self) -> bool:
        return self.open is not None

    def to_row(self) -> dict:
        assert self.bar_ts is not None
        return {
            "symbol": self.symbol,
            "timestamp": self.bar_ts,
            "open": float(self.open or 0.0),
            "high": float(self.high or 0.0),
            "low": float(self.low or 0.0),
            "close": float(self.close or 0.0),
            "adj_close": float(self.close or 0.0),
            "volume": float(self.volume),
            "source": "vn_ws",
            "ingestion_time": datetime.now(timezone.utc),
        }


def _truncate_to_minute(ts: datetime) -> datetime:
    """Return ``ts`` floored to the start of its minute (UTC, tz-aware)."""

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.replace(second=0, microsecond=0)


# ─────────────────────────────────────────────────────────────────────────────
# Publisher
# ─────────────────────────────────────────────────────────────────────────────


class VNStreamPublisher:
    """Aggregate SSI iBoard ticks into 1-minute OHLCV bars and publish."""

    def __init__(
        self,
        symbols: Iterable[str] | None = None,
        bootstrap_servers: str | None = None,
        topic: str = TOPIC_OHLCV_RAW,
        flush_interval_seconds: float = 5.0,
        batch_size: int = 100,
        boards: Iterable[str] | None = None,
    ) -> None:
        self.symbols = [
            s.strip().upper()
            for s in (symbols or settings.vn_ws_symbols.split(","))
            if s.strip()
        ]
        if not self.symbols:
            raise ValueError("At least one VN symbol must be supplied.")

        self.bootstrap_servers = (
            bootstrap_servers
            or settings.kafka_bootstrap_servers
            or DEFAULT_BOOTSTRAP_SERVERS
        )
        self.topic = topic
        self.flush_interval_seconds = max(1.0, float(flush_interval_seconds))
        self.batch_size = batch_size
        self.boards = (
            [b.strip().upper() for b in boards]
            if boards
            else [b.strip().upper() for b in (settings.vn_ws_boards or "").split(",") if b.strip()]
        ) or list(DEFAULT_BOARDS)

        self._producer = StockKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        self._client: VNWebSocketClient | None = None
        self._rest_poller: VNRestPoller | None = None
        self._flush_thread: threading.Thread | None = None
        self._running = False

        # Per-symbol 1-minute OHLCV aggregator buffer
        self._bars: dict[str, _BarAccumulator] = defaultdict(_BarAccumulator)
        self._buffer_lock = threading.Lock()
        self._sent_count = 0

    # ──────────────────────────────────────────────────── public

    def start(self) -> None:
        if self._running:
            logger.warning("VNStreamPublisher already running")
            return

        if not self._producer.bootstrap_servers:
            raise RuntimeError(
                "Kafka bootstrap servers are not configured. "
                "Set KAFKA_BOOTSTRAP_SERVERS in .env."
            )

        self._running = True
        self._client = build_default_client(
            symbols=self.symbols,
            on_message=self._handle_message,
        )
        # boards/dead-man come from settings via build_default_client
        self._client.connect(blocking=False)

        # REST fallback - always-on so off-hours still produces data
        self._rest_poller = VNRestPoller(
            symbols=self.symbols,
            kafka_topic=self.topic,
            bootstrap_servers=self.bootstrap_servers,
        )
        try:
            self._rest_poller.start()
        except Exception as exc:  # noqa: BLE001
            logger.warning("VN REST poller failed to start: %s", exc)
            self._rest_poller = None

        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="vn-publisher-flush"
        )
        self._flush_thread.start()

        logger.info(
            "VNStreamPublisher started: symbols=%d topic=%s broker=%s "
            "rest_poller=%s boards=%s",
            len(self.symbols),
            self.topic,
            self.bootstrap_servers,
            "on" if self._rest_poller is not None else "off",
            self.boards,
        )

    def stop(self) -> None:
        self._running = False
        if self._client is not None:
            self._client.stop()
            self._client = None
        if self._rest_poller is not None:
            self._rest_poller.stop()
            self._rest_poller = None
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=5)
            self._flush_thread = None
        # Flush any remaining buffered bars synchronously
        self._flush_buffers(force=True)
        self._producer.close()
        logger.info("VNStreamPublisher stopped (published=%d bars)", self._sent_count)

    def published_count(self) -> int:
        return self._sent_count

    # ──────────────────────────────────────────────────── internals

    def _handle_message(self, tick: VNQuoteTick) -> None:
        """Fold a single tick into the per-symbol 1-minute bar buffer."""

        if not tick.symbol or tick.price is None or tick.price <= 0:
            return

        sym = tick.symbol.upper()
        bar_ts = _truncate_to_minute(tick.ts)

        with self._buffer_lock:
            bar = self._bars[sym]
            # Roll a new bar if we just crossed into a new minute.
            if bar.bar_ts is None:
                bar.symbol = sym
                bar.bar_ts = bar_ts
            elif bar.bar_ts != bar_ts:
                self._emit_bar(sym, bar)
                self._bars[sym] = _BarAccumulator(symbol=sym, ts=bar_ts)
                bar = self._bars[sym]
            bar.update(tick)

    def _flush_loop(self) -> None:
        while self._running:
            time.sleep(self.flush_interval_seconds)
            try:
                self._flush_buffers(force=False)
            except Exception as exc:  # noqa: BLE001
                logger.error("VNStreamPublisher flush error: %s", exc)

    def _flush_buffers(self, force: bool) -> None:
        with self._buffer_lock:
            rows: list[dict] = []
            now = datetime.now(timezone.utc)
            for sym, bar in list(self._bars.items()):
                if not bar.is_complete():
                    continue
                # Force flush at stop; otherwise only flush bars whose minute
                # is fully in the past.
                if force:
                    rows.append(bar.to_row())
                    self._bars[sym] = _BarAccumulator()
                else:
                    assert bar.bar_ts is not None
                    age = (now - bar.bar_ts).total_seconds()
                    if age >= 60.0:  # bar's minute closed
                        rows.append(bar.to_row())
                        self._bars[sym] = _BarAccumulator()

        if not rows:
            return

        frame = pd.DataFrame(rows)
        try:
            # Single bar → keyed by symbol; multi-bar → batched under "batch".
            if len(frame) == 1:
                sent = self._producer.send_ohlcv_stream(
                    frame["symbol"].iloc[0], frame, topic=self.topic
                )
            else:
                sent = self._producer.send_ohlcv_stream(
                    "batch", frame, topic=self.topic
                )
            self._sent_count += sent
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to publish VN bar batch: %s", exc)

    def _emit_bar(self, sym: str, bar: _BarAccumulator) -> None:
        """Push a single (out-of-window) bar to Kafka immediately."""

        if not bar.is_complete():
            return
        frame = pd.DataFrame([bar.to_row()])
        try:
            sent = self._producer.send_ohlcv_stream(sym, frame, topic=self.topic)
            self._sent_count += sent
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to publish %s VN bar: %s", sym, exc)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def parse_args():  # pragma: no cover - CLI helper
    import argparse

    parser = argparse.ArgumentParser(
        description="Stream SSI iBoard WebSocket → Kafka (1-minute OHLCV bars)"
    )
    parser.add_argument("--symbols", default=None, help="Comma-separated VN tickers")
    parser.add_argument(
        "--boards", default=None, help="Comma-separated board IDs (MAIN, HNX, UPCOM)"
    )
    parser.add_argument("--topic", default=TOPIC_OHLCV_RAW)
    parser.add_argument(
        "--bootstrap",
        default=settings.kafka_bootstrap_servers or DEFAULT_BOOTSTRAP_SERVERS,
    )
    parser.add_argument("--interval", type=float, default=5.0, help="Flush interval (s)")
    parser.add_argument(
        "--duration", type=int, default=0,
        help="Stop after N seconds (0 = run forever).",
    )
    return parser.parse_args()


def _main():  # pragma: no cover - CLI helper
    args = parse_args()
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
    publisher.start()
    try:
        if args.duration > 0:
            time.sleep(args.duration)
            publisher.stop()
        else:
            while True:
                time.sleep(1)
                if publisher.published_count() and publisher.published_count() % 50 == 0:
                    logger.info("Published %d bars so far", publisher.published_count())
    except KeyboardInterrupt:
        publisher.stop()


if __name__ == "__main__":  # pragma: no cover
    _main()
