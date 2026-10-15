"""Streaming service — Kafka bridge with in-memory cache.

Maintains the most-recent bars per symbol in a thread-safe in-memory cache
so the REST layer can serve `/api/v1/stream/latest` without exposing Kafka
internals to the frontend.

Two modes:

- ``consumer`` (background): subscribes to a Kafka topic and updates the
  cache whenever a new bar arrives. Off by default unless ``USE_KAFKA=true``.
- ``manual``  (fallback): a cron / publisher pushes bars via
  ``record_bar(symbol, bar)``; works even without Kafka.

The cache is a ``deque(maxlen=N)`` per symbol so old data is evicted on a
rolling window basis (default 240 bars = 4 hours of 1-minute data).
"""

from __future__ import annotations

import queue
import threading
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

_DEFAULT_WINDOW = 240


@dataclass(slots=True)
class StreamBar:
    """One bar in the streaming cache.

    ``symbol`` is denormalised so the cache can be flattened without an extra
    join when serialised to JSON.
    """

    symbol: str
    timestamp: str
    high: float
    low: float
    open: float
    close: float
    volume: float
    source: str = "kafka"
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_kafka(cls, payload: dict[str, Any]) -> "StreamBar":
        """Build a StreamBar from a Kafka deserialised JSON payload."""
        ts = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
        return cls(
            symbol=str(payload.get("symbol", "")).upper(),
            timestamp=str(ts),
            open=float(payload.get("open", 0.0) or 0.0),
            high=float(payload.get("high", 0.0) or 0.0),
            low=float(payload.get("low", 0.0) or 0.0),
            close=float(payload.get("close", 0.0) or 0.0),
            volume=float(payload.get("volume", 0.0) or 0.0),
            source=str(payload.get("source", "kafka")),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class StreamCache:
    """Thread-safe rolling buffer of StreamBars per symbol.

    Doubles as a tiny pub/sub bus: any code path that records a bar
    (``record``, ``record_bar``, ``publish_bar``) also notifies every
    subscriber registered via :meth:`subscribe`. The SSE endpoint in
    ``app.api.v1.endpoints.stream`` uses this to push bars to connected
    browsers in real time.
    """

    def __init__(self, window: int = _DEFAULT_WINDOW) -> None:
        self._window = window
        self._buffers: dict[str, deque[StreamBar]] = {}
        self._lock = threading.Lock()
        self._total_recorded = 0
        self._started_at = datetime.now(timezone.utc).isoformat()
        # Subscribers: list of thread-safe queues drained by SSE consumers.
        # We use a list + GIL-bound append (subscriber count is small) and
        # wrap each queue in a lock-free interface so producers never block
        # the Kafka consumer thread.
        self._subscribers: list["queue.Queue[StreamBar]"] = []

    # ── pub/sub ──────────────────────────────────────────────────────────
    def subscribe(self) -> "queue.Queue[StreamBar]":
        """Register a new SSE consumer and return its inbox queue.

        The caller is responsible for calling :meth:`unsubscribe` (or
        simply closing the queue) when the client disconnects.
        """
        import queue

        q: "queue.Queue[StreamBar]" = queue.Queue(maxsize=1024)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[StreamBar]") -> None:
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def _notify(self, bar: StreamBar) -> None:
        # Snapshot outside the lock to avoid holding it during queue.put.
        with self._lock:
            subs = list(self._subscribers)
        for q in subs:
            # Drop the oldest item if the consumer is too slow instead of
            # blocking the producer (which would back up the Kafka loop).
            try:
                q.put_nowait(bar)
            except Exception:  # noqa: BLE001 - queue.Full or closed
                try:
                    q.get_nowait()
                    q.put_nowait(bar)
                except Exception:  # pragma: no cover
                    pass

    # ── record / read ────────────────────────────────────────────────────
    def record(self, bar: StreamBar) -> None:
        with self._lock:
            buf = self._buffers.get(bar.symbol)
            if buf is None:
                buf = deque(maxlen=self._window)
                self._buffers[bar.symbol] = buf
            buf.append(bar)
            self._total_recorded += 1
        # Notify outside the lock so subscribers can never deadlock the
        # producer by holding the cache lock while waiting on a slow client.
        self._notify(bar)

    def latest(self, symbol: str) -> StreamBar | None:
        with self._lock:
            buf = self._buffers.get(symbol.upper())
            if not buf:
                return None
            return buf[-1]

    def history(self, symbol: str, limit: int = 60) -> list[StreamBar]:
        with self._lock:
            buf = self._buffers.get(symbol.upper())
            if not buf:
                return []
            return list(buf)[-limit:]

    def symbols(self) -> list[str]:
        with self._lock:
            return sorted(self._buffers.keys())

    def snapshot(self) -> dict[str, StreamBar]:
        """Return the latest bar for every tracked symbol."""
        with self._lock:
            return {sym: buf[-1] for sym, buf in self._buffers.items() if buf}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "symbols_tracked": len(self._buffers),
                "total_recorded": self._total_recorded,
                "started_at": self._started_at,
                "uptime_seconds": (datetime.now(timezone.utc) - datetime.fromisoformat(self._started_at)).total_seconds(),
            }


# Module-level singleton. Imported by the REST layer and the Kafka consumer
# bridge so both share the same buffer without re-instantiation.
_cache = StreamCache()


def get_cache() -> StreamCache:
    return _cache


# ── Kafka consumer bridge ────────────────────────────────────────────────────────

_consumer_thread: threading.Thread | None = None
_consumer_stop = threading.Event()


def _consume_loop(topic: str, bootstrap_servers: str) -> None:
    """Background loop: poll Kafka and record each bar into the cache."""
    try:
        from kafka import KafkaConsumer
    except ImportError:
        logger.warning("kafka-python not installed; stream cache will stay empty")
        return

    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=[bootstrap_servers] if isinstance(bootstrap_servers, str) else bootstrap_servers,
            group_id="stock-lakehouse-stream-cache",
            value_deserializer=lambda v: v,  # we use StreamBar.from_kafka for shape
            auto_offset_reset="latest",  # only care about new ticks at startup
            enable_auto_commit=True,
            session_timeout_ms=10000,
            heartbeat_interval_ms=3000,
        )
    except Exception as exc:
        logger.warning("Kafka consumer init failed (%s); cache empty", exc)
        return

    logger.info("Stream cache consumer started on topic=%s", topic)
    try:
        while not _consumer_stop.is_set():
            try:
                records = consumer.poll(timeout_ms=1000)
                for _tp, messages in records.items():
                    for msg in messages:
                        try:
                            payload = _parse_payload(msg.value)
                            if payload is None:
                                continue
                            bar = StreamBar.from_kafka(payload)
                            if bar.symbol:
                                _cache.record(bar)
                        except Exception as exc:  # noqa: BLE001 - one bad msg must not kill the loop
                            logger.debug("Skipping malformed stream message: %s", exc)
            except Exception as exc:  # noqa: BLE001 - kafka transient errors
                logger.warning("Stream consumer poll error: %s", exc)
                time.sleep(2)
    finally:
        try:
            consumer.close()
        except Exception:  # pragma: no cover
            pass
        logger.info("Stream cache consumer stopped")


def _parse_payload(raw: bytes | None) -> dict[str, Any] | None:
    if not raw:
        return None
    import json

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    # Single-bar payload: has 'open'/'close' directly. Batch payload:
    # {'symbol': ..., 'bars': [...]} — flatten each bar into its own record.
    if isinstance(data, dict) and isinstance(data.get("bars"), list):
        for bar in data["bars"]:
            if isinstance(bar, dict):
                bar.setdefault("symbol", data.get("symbol", ""))
                _cache.record(StreamBar.from_kafka(bar))
        return None
    return data if isinstance(data, dict) else None


def start_consumer_background(
    topics: Iterable[str] | None = None,
    bootstrap_servers: str | None = None,
) -> None:
    """Start a daemon thread that drains Kafka into the cache.

    Idempotent: calling twice is a no-op. Honors ``settings.use_kafka`` —
    if Kafka is disabled the call is skipped so the REST layer still works
    for manually-published bars.
    """
    global _consumer_thread

    if not settings.use_kafka:
        logger.info("USE_KAFKA=false; stream consumer not started")
        return

    if _consumer_thread is not None and _consumer_thread.is_alive():
        logger.debug("Stream consumer already running")
        return

    topic_list = list(topics or ("stock-ohlcv-raw",))
    servers = bootstrap_servers or settings.kafka_bootstrap_servers

    _consumer_stop.clear()
    _consumer_thread = threading.Thread(
        target=_consume_loop,
        args=(topic_list[0], servers),
        daemon=True,
        name="stream-cache-consumer",
    )
    _consumer_thread.start()


def stop_consumer_background() -> None:
    global _consumer_thread
    _consumer_stop.set()
    if _consumer_thread is not None:
        _consumer_thread.join(timeout=5)
        _consumer_thread = None


# ── Producer helper (publishes one bar to Kafka; used by /stream/ingest) ───────

def publish_bar(symbol: str, bar: dict[str, Any], topic: str = "stock-ohlcv-raw") -> bool:
    """Publish a single bar to Kafka and record it in the local cache."""
    payload = {
        "symbol": symbol.upper(),
        "timestamp": bar.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "open": float(bar.get("open", 0.0) or 0.0),
        "high": float(bar.get("high", 0.0) or 0.0),
        "low": float(bar.get("low", 0.0) or 0.0),
        "close": float(bar.get("close", 0.0) or 0.0),
        "volume": float(bar.get("volume", 0.0) or 0.0),
        "source": bar.get("source", "manual"),
    }
    sent = False
    if settings.use_kafka:
        try:
            from app.streaming.kafka_producer import StockKafkaProducer

            producer = StockKafkaProducer()
            producer.send_ohlcv(symbol.upper(), _payload_to_df(payload), topic=topic)
            sent = True
        except Exception as exc:  # noqa: BLE001 - producer must not block the API
            logger.warning("Kafka publish failed for %s: %s", symbol, exc)

    _cache.record(StreamBar.from_kafka(payload))
    return sent


def _payload_to_df(payload: dict[str, Any]):
    """Convert one bar dict to a 1-row DataFrame the producer accepts."""
    import pandas as pd

    return pd.DataFrame([payload])


def record_bar(symbol: str, bar: dict[str, Any]) -> None:
    """Cache-only entry point used by tests / scripts that bypass Kafka."""
    payload = {
        "symbol": symbol.upper(),
        "timestamp": bar.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "open": float(bar.get("open", 0.0) or 0.0),
        "high": float(bar.get("high", 0.0) or 0.0),
        "low": float(bar.get("low", 0.0) or 0.0),
        "close": float(bar.get("close", 0.0) or 0.0),
        "volume": float(bar.get("volume", 0.0) or 0.0),
        "source": bar.get("source", "manual"),
    }
    _cache.record(StreamBar.from_kafka(payload))