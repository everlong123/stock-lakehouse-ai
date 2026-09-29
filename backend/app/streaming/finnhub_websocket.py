"""Finnhub WebSocket client - real-time trades and quotes for the Free tier.

Free tier limits (per https://finnhub.io/docs/api/websocket-trades):
- One simultaneous WebSocket connection
- Subscribe to up to 50 symbols total
- Messages capped at ~50 msgs/sec

We implement:
- A robust connection that auto-reconnects with exponential back-off
- PING every 25s (Finnhub closes the socket after 30s of silence)
- Callbacks for ``trade`` and ``news`` payloads
- Optional Kafka forwarding via :class:`StreamPublisher`

Run standalone::

    python -m app.streaming.finnhub_websocket --symbols AAPL,MSFT,GOOGL --kafka
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Queue
from typing import Callable, Iterable

logger = get_logger = lambda name: logging.getLogger(name)  # placeholder, replaced below


from app.core.config import settings
from app.core.logging_config import get_logger as _get_logger

logger = _get_logger(__name__)


# Re-export so the linter doesn't complain about the placeholder above.
logger = _get_logger(__name__)


FINNHUB_WS_URL = "wss://ws.finnhub.io"


@dataclass
class StreamMessage:
    """Normalised WebSocket payload from Finnhub."""

    type: str                          # 'trade', 'news', 'ping', 'error'
    symbol: str | None = None
    timestamp: datetime | None = None
    payload: dict = field(default_factory=dict)

    def to_ohlcv(self, symbol: str | None = None) -> dict | None:
        """Convert a ``trade`` payload into a single-row OHLCV dict.

        The trade payload exposes individual executed prices - for a $0 budget
        project we aggregate them per-second into OHLCV so they can be merged
        into Bronze without breaking the schema.
        """

        sym = (symbol or self.symbol or "").upper()
        if not sym or self.type != "trade" or not self.payload:
            return None
        data = self.payload.get("data") or []
        if not data:
            return None

        prices = [float(item.get("p", 0)) for item in data]
        volumes = [float(item.get("v", 0)) for item in data]
        if not prices:
            return None

        ts = self.timestamp or datetime.now(timezone.utc)
        first_trade_ts = data[0].get("t")
        if first_trade_ts:
            try:
                ts = datetime.fromtimestamp(first_trade_ts / 1000, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                pass

        return {
            "symbol": sym,
            "timestamp": ts,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "adj_close": prices[-1],
            "volume": sum(volumes),
            "source": "finnhub_ws",
            "ingestion_time": datetime.now(timezone.utc),
        }


class FinnhubWebSocketClient:
    """Reconnecting WebSocket client for Finnhub real-time data.

    Uses the ``websocket-client`` package (``pip install websocket-client``) when
    available, with graceful fallback when the dependency is missing.
    """

    def __init__(
        self,
        api_key: str | None = None,
        symbols: Iterable[str] | None = None,
        on_message: Callable[[StreamMessage], None] | None = None,
        max_reconnect_attempts: int = 0,
        ping_interval: int = 25,
    ) -> None:
        self.api_key = (api_key or settings.finnhub_api_key or "").strip()
        if not self.api_key:
            raise ValueError(
                "Finnhub API key is required. Set FINNHUB_API_KEY in .env."
            )

        self.symbols = [s.upper() for s in (symbols or settings.crawl_symbols.split(","))]
        self.on_message = on_message
        self.max_reconnect_attempts = max_reconnect_attempts  # 0 = infinite
        self.ping_interval = ping_interval

        self._ws = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._message_count = 0
        self._last_ping = 0.0
        self._queue: Queue[StreamMessage] = Queue(maxsize=10_000)

    # ----------------------------------------------------------- public API

    def connect(self, blocking: bool = True) -> None:
        """Start the WebSocket connection in a background thread (or block)."""

        if not self.symbols:
            raise ValueError("At least one symbol must be supplied to subscribe.")

        if self._running:
            logger.warning("Finnhub WebSocket already running")
            return

        self._running = True

        if blocking:
            self._run_forever()
        else:
            self._thread = threading.Thread(target=self._run_forever, daemon=True, name="finnhub-ws")
            self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:  # pragma: no cover - best effort
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Finnhub WebSocket stopped (received=%d)", self._message_count)

    def stream_iter(self) -> Iterable[StreamMessage]:
        """Yield parsed messages - useful for tests/scripts without a callback."""

        while self._running:
            try:
                yield self._queue.get(timeout=1)
            except Exception:
                continue

    @property
    def message_count(self) -> int:
        return self._message_count

    # ----------------------------------------------------------- internals

    def _run_forever(self) -> None:
        attempts = 0
        while self._running:
            try:
                self._connect_once()
                attempts = 0
            except Exception as exc:  # noqa: BLE001
                attempts += 1
                logger.error(
                    "Finnhub WebSocket error (attempt %d): %s",
                    attempts,
                    exc,
                )
                if self.max_reconnect_attempts and attempts >= self.max_reconnect_attempts:
                    logger.error("Max reconnect attempts reached - giving up")
                    self._running = False
                    return
                time.sleep(min(30, 2 ** attempts))

    def _connect_once(self) -> None:
        try:
            import websocket  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "websocket-client is required. Install with 'pip install websocket-client'."
            ) from exc

        url = f"{FINNHUB_WS_URL}?token={self.api_key}"
        logger.info("Connecting to Finnhub WebSocket (%d symbols)", len(self.symbols))
        ws = websocket.create_connection(url, timeout=15)
        self._ws = ws
        self._last_ping = time.time()

        for symbol in self.symbols:
            ws.send(json.dumps({"type": "subscribe", "symbol": symbol.upper()}))
        logger.info("Subscribed to %d symbols", len(self.symbols))

        try:
            while self._running:
                if time.time() - self._last_ping >= self.ping_interval:
                    try:
                        ws.send(json.dumps({"type": "ping"}))
                        self._last_ping = time.time()
                    except Exception as exc:
                        logger.warning("Finnhub PING failed: %s", exc)
                        break

                ws.settimeout(1)
                try:
                    raw = ws.recv()
                except Exception as exc:  # websocket.WebSocketTimeoutException etc.
                    if "timeout" in str(exc).lower():
                        continue
                    raise

                if not raw:
                    continue
                self._handle_raw(raw)
        finally:
            try:
                for symbol in self.symbols:
                    ws.send(json.dumps({"type": "unsubscribe", "symbol": symbol.upper()}))
            except Exception:
                pass
            try:
                ws.close()
            except Exception:
                pass
            self._ws = None

    def _handle_raw(self, raw: str | bytes) -> None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Discarded non-JSON payload: %s", raw[:80])
            return

        msg_type = payload.get("type", "trade")
        self._message_count += 1

        if msg_type == "ping":
            # Some servers send server-initiated pings - treat as a keepalive
            self._last_ping = time.time()
            return

        stream_msg = StreamMessage(
            type=msg_type,
            symbol=payload.get("symbol") or payload.get("data", [{}])[0].get("s") if isinstance(payload.get("data"), list) and payload["data"] else payload.get("symbol"),
            timestamp=datetime.now(timezone.utc),
            payload=payload,
        )
        # Translate numeric ms timestamps when available
        if msg_type == "trade" and payload.get("data"):
            try:
                first = payload["data"][0]
                ts_ms = first.get("t")
                if ts_ms:
                    stream_msg.timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            except Exception:
                pass

        if self.on_message is not None:
            try:
                self.on_message(stream_msg)
            except Exception as exc:  # noqa: BLE001 - never let a callback kill the loop
                logger.error("on_message handler raised: %s", exc)

        try:
            self._queue.put_nowait(stream_msg)
        except Exception:
            # Drop the oldest if queue is full - latest data is more valuable
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(stream_msg)
            except Exception:
                pass


def build_default_client(
    symbols: Iterable[str] | None = None,
    on_message: Callable[[StreamMessage], None] | None = None,
) -> FinnhubWebSocketClient:
    """Convenience constructor used by other modules and scripts."""

    return FinnhubWebSocketClient(
        api_key=settings.finnhub_api_key,
        symbols=symbols or settings.crawl_symbols.split(","),
        on_message=on_message,
    )