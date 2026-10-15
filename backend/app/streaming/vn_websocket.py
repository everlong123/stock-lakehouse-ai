"""Vietnamese stock real-time WebSocket client - SSI iBoard pushstream.

The public endpoint ``wss://iboard-pushstream.ssi.com.vn/realtime`` is the
same one the website ``iboard.ssi.com.vn`` uses to push real-time price
updates to its browser clients. It is free, anonymous and does NOT require
any API key, consumer secret or login.

The protocol is a *GraphQL-over-WebSocket* subscribe stream:

    1. On ``onopen`` the client sends a subscription JSON with the list of
       symbols and the board filter (HOSE/HNX/UPCOM). The same JSON is
       re-sent after every reconnect.

    2. The server pushes data in two shapes:

       - **Quote tick** — a single ``"|"`` (pipe) delimited string of
         ~70 numeric fields. The relevant offsets are documented in
         :func:`parse_quote` below. All monetary values are reported in
         *thousand VND* and must be divided by 1000 to get absolute VND.

       - **Control / error** — a JSON object containing an ``error`` key
         which we treat as a reconnect trigger.

    3. The server has NO client-side ping/pong. To detect a dead socket
       we use a dead-man timer — if no message has been received in
       ``dead_man_timeout`` seconds we drop the connection and let the
       reconnect loop resubscribe.

    4. Reconnects use exponential backoff. The first attempt waits 3s,
       then 6s, 12s, 24s, capped at 60s. After ``max_reconnect_attempts``
       (default 10) consecutive failures the client gives up.

Source of truth for the field offsets: ``vnstock-js@1.5.1`` decompiled
output (https://cdn.jsdelivr.net/npm/vnstock-js@1.5.1/dist/realtime/index.js).
A runnable Python example is provided at the bottom of this file in the
``__main__`` block — useful for manual smoke-tests during trading hours.
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

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

#: The WebSocket endpoint used by ``iboard.ssi.com.vn`` to push live quotes
VN_WS_URL = "wss://iboard-pushstream.ssi.com.vn/realtime"

#: Default exchange boards to subscribe to.  HOSE = "MAIN", HNX, UPCOM.
DEFAULT_BOARDS: tuple[str, ...] = ("MAIN", "HNX", "UPCOM")

#: Subscribe topic — every quote-stream subscription uses this string.
#: (This is a graphql-over-ws subscription topic.)
SUBSCRIBE_TOPIC = "stockRealtimeBySymbolsAndBoards"

#: Field index map (kept as module constants so the parser is self-documenting).
#: Names come from the vnstock-js ``parseData`` function.
IDX_EXCHANGE = 0
IDX_ID = 1
IDX_BID1_P = 2
IDX_BID1_V = 3
IDX_BID2_P = 4
IDX_BID2_V = 5
IDX_BID3_P = 6
IDX_BID3_V = 7
IDX_ASK1_P = 22
IDX_ASK1_V = 23
IDX_ASK2_P = 24
IDX_ASK2_V = 25
IDX_ASK3_P = 26
IDX_ASK3_V = 27
IDX_MATCHED_P = 42
IDX_MATCHED_V = 43
IDX_FOREIGN_BUY_VOL = 48
IDX_FOREIGN_BUY_VAL = 49
IDX_CHANGE = 52
IDX_CHANGE_PCT = 53
IDX_TOTAL_VOL = 54
IDX_TOTAL_VAL = 55
IDX_LAST_UPDATED = 65
IDX_SIDE = 66

#: Number of pipe-delimited fields expected in a well-formed tick.
#: A well-formed tick from SSI always has >= 67 fields.
EXPECTED_FIELD_COUNT = 67

# ─────────────────────────────────────────────────────────────────────────────
# Data class
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class VNQuoteTick:
    """A single real-time quote tick parsed from the SSI iBoard push stream."""

    symbol: str
    exchange: str
    ts: datetime               # when the server reported the tick
    price: float               # matched price in VND (already ÷ 1000)
    volume: float              # volume of the last matched print
    change: float              # change vs reference, VND
    change_pct: float          # change percent (e.g. 1.44 = 1.44%)
    bid: float | None = None   # best bid price in VND
    ask: float | None = None   # best ask price in VND
    bid_volume: float | None = None
    ask_volume: float | None = None
    total_volume: float = 0.0
    total_value: float = 0.0
    side: str = "unknown"      # "buy" or "sell" (aggressor side of last print)
    raw: str = ""              # the raw pipe-delimited string (for debugging)


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────


def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_quote(raw: str) -> VNQuoteTick | None:
    """Parse a pipe-delimited SSI quote tick into a :class:`VNQuoteTick`.

    Returns ``None`` if the message is too short or the symbol cannot be
    extracted. The caller is expected to log + drop the tick in that case.
    """

    if not raw or "|" not in raw:
        return None

    parts = raw.split("|")
    if len(parts) < EXPECTED_FIELD_COUNT:
        logger.debug("Discarded short quote tick (fields=%d): %s", len(parts), raw[:80])
        return None

    # Symbol comes from the "X#FPT" id field; everything after '#' is the
    # ticker.
    raw_id = parts[IDX_ID] or ""
    symbol = raw_id.split("#", 1)[1] if "#" in raw_id else ""
    if not symbol:
        logger.debug("Discarded tick with empty symbol: %s", raw[:80])
        return None

    # SSI reports monetary values in *thousand VND* — convert to absolute VND.
    matched_price = _safe_int(parts[IDX_MATCHED_P]) / 1000.0
    bid1 = _safe_int(parts[IDX_BID1_P]) / 1000.0
    ask1 = _safe_int(parts[IDX_ASK1_P]) / 1000.0
    change = _safe_int(parts[IDX_CHANGE]) / 1000.0
    change_pct = _safe_int(parts[IDX_CHANGE_PCT]) / 100.0

    matched_volume = float(_safe_int(parts[IDX_MATCHED_V]))
    bid1_volume = _safe_int(parts[IDX_BID1_V])
    ask1_volume = _safe_int(parts[IDX_ASK1_V])

    total_volume = float(_safe_int(parts[IDX_TOTAL_VOL]))
    total_value = float(_safe_int(parts[IDX_TOTAL_VAL]))

    last_updated_ms = _safe_int(parts[IDX_LAST_UPDATED])
    if last_updated_ms > 0:
        try:
            ts = datetime.fromtimestamp(last_updated_ms / 1000.0, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            ts = datetime.now(timezone.utc)
    else:
        ts = datetime.now(timezone.utc)

    side_raw = (parts[IDX_SIDE] or "").strip().lower()
    side = "buy" if side_raw == "b" else ("sell" if side_raw == "s" else "unknown")

    return VNQuoteTick(
        symbol=symbol.upper(),
        exchange=(parts[IDX_EXCHANGE] or "").upper(),
        ts=ts,
        price=matched_price,
        volume=matched_volume,
        change=change,
        change_pct=change_pct,
        bid=bid1 if bid1 > 0 else None,
        ask=ask1 if ask1 > 0 else None,
        bid_volume=float(bid1_volume) if bid1_volume > 0 else None,
        ask_volume=float(ask1_volume) if ask1_volume > 0 else None,
        total_volume=total_volume,
        total_value=total_value,
        side=side,
        raw=raw,
    )


def _build_subscribe_message(symbols: Iterable[str], boards: Iterable[str]) -> str:
    """Return a JSON subscription message ready to be sent on the socket.

    The shape is the same one used by ``vnstock-js`` Realtime client.
    """

    return json.dumps(
        {
            "type": "sub",
            "topic": SUBSCRIBE_TOPIC,
            "variables": {
                "symbols": [s.upper() for s in symbols],
                "boardIds": list(boards),
            },
            "component": "priceTableEquities",
        },
        separators=(",", ":"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────


class VNWebSocketClient:
    """Auto-reconnecting WebSocket client for SSI iBoard real-time quotes.

    The client follows the same lifecycle as :class:`FinnhubWebSocketClient`
    so the two providers can be swapped behind a single publisher
    abstraction: a background thread holds the socket, a queue buffers
    parsed ticks, a dead-man thread enforces liveness.
    """

    def __init__(
        self,
        symbols: Iterable[str] | None = None,
        on_message: Callable[[VNQuoteTick], None] | None = None,
        boards: Iterable[str] = DEFAULT_BOARDS,
        max_reconnect_attempts: int = 10,
        dead_man_timeout: float = 60.0,
        queue_maxsize: int = 10_000,
    ) -> None:
        if symbols is None:
            raw_symbols = settings.vn_ws_symbols.split(",")
        else:
            raw_symbols = list(symbols)
        self.symbols = [s.strip().upper() for s in raw_symbols]
        self.symbols = [s for s in self.symbols if s]  # drop empties / whitespace-only
        if not self.symbols:
            raise ValueError(
                "At least one VN symbol must be supplied to subscribe. "
                "Set VN_WS_SYMBOLS in .env or pass a non-empty symbols list."
            )

        self.boards = [b.upper() for b in boards] if boards else list(DEFAULT_BOARDS)
        self.on_message = on_message
        self.max_reconnect_attempts = max_reconnect_attempts  # 0 = infinite
        self.dead_man_timeout = float(dead_man_timeout)

        self._ws = None
        self._thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._message_count = 0
        self._last_message_at: float = 0.0
        self._queue: Queue[VNQuoteTick] = Queue(maxsize=queue_maxsize)

    # ──────────────────────────────────────────────────── public API

    def connect(self, blocking: bool = True) -> None:
        """Start the WebSocket in a background thread (or block)."""

        if self._running:
            logger.warning("VN WebSocket already running")
            return

        self._running = True
        self._last_message_at = time.time()
        if blocking:
            self._run_forever()
        else:
            self._thread = threading.Thread(
                target=self._run_forever, daemon=True, name="vn-ws"
            )
            self._thread.start()
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop, daemon=True, name="vn-ws-heartbeat"
            )
            self._heartbeat_thread.start()

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
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2)
            self._heartbeat_thread = None
        logger.info("VN WebSocket stopped (received=%d)", self._message_count)

    def stream_iter(self) -> Iterable[VNQuoteTick]:
        """Yield parsed ticks — useful for tests and scripts."""

        while self._running:
            try:
                yield self._queue.get(timeout=1)
            except Exception:
                continue

    @property
    def message_count(self) -> int:
        return self._message_count

    # ──────────────────────────────────────────────────── internals

    def _run_forever(self) -> None:
        attempts = 0
        while self._running:
            try:
                self._connect_once()
                attempts = 0
            except Exception as exc:  # noqa: BLE001
                attempts += 1
                logger.error(
                    "VN WebSocket error (attempt %d): %s", attempts, exc
                )
                if (
                    self.max_reconnect_attempts
                    and attempts >= self.max_reconnect_attempts
                ):
                    logger.error("Max reconnect attempts reached - giving up")
                    self._running = False
                    return
                time.sleep(min(60, 3 * (2 ** (attempts - 1))))

    def _connect_once(self) -> None:
        try:
            import websocket  # type: ignore
        except ImportError as exc:  # pragma: no cover - env check
            raise RuntimeError(
                "websocket-client is required. Install with 'pip install websocket-client'."
            ) from exc

        logger.info(
            "Connecting to SSI iBoard WebSocket (%d symbols, boards=%s)",
            len(self.symbols),
            self.boards,
        )
        ws = websocket.create_connection(VN_WS_URL, timeout=15)
        self._ws = ws

        # SSI subscribes to one topic at a time, and accepts multiple
        # board filters in a single message. We send a single sub JSON.
        sub = _build_subscribe_message(self.symbols, self.boards)
        ws.send(sub)
        logger.info(
            "Subscribed to %d symbols across boards=%s", len(self.symbols), self.boards
        )

        try:
            while self._running:
                ws.settimeout(1)
                try:
                    raw = ws.recv()
                except Exception as exc:  # noqa: BLE001
                    if "timeout" in str(exc).lower():
                        continue
                    raise
                if not raw:
                    continue
                self._handle_raw(raw)
        finally:
            try:
                ws.close()
            except Exception:
                pass
            self._ws = None

    def _heartbeat_loop(self) -> None:
        """Force a reconnect if no message has been received in dead_man_timeout."""

        while self._running:
            time.sleep(min(10.0, self.dead_man_timeout / 2.0))
            if not self._running:
                return
            silence = time.time() - self._last_message_at
            if silence > self.dead_man_timeout and self._ws is not None:
                logger.warning(
                    "No VN tick for %.0fs — forcing reconnect (dead-man timer)",
                    silence,
                )
                try:
                    self._ws.close()
                except Exception:
                    pass
                # _run_forever will catch the resulting exception and backoff
                self._ws = None

    def _handle_raw(self, raw: str | bytes) -> None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        if not raw:
            return

        with self._lock:
            self._message_count += 1
            self._last_message_at = time.time()

        # Control / error messages are JSON with an ``error`` key. We log
        # them and rely on the dead-man timer to reconnect if the stream
        # actually stops.
        if raw.startswith("{"):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                logger.debug("Discarded malformed JSON: %s", raw[:80])
                return
            if "error" in payload:
                logger.warning("VN WebSocket server error: %s", payload.get("error"))
            return

        tick = parse_quote(raw)
        if tick is None:
            return

        if self.on_message is not None:
            try:
                self.on_message(tick)
            except Exception as exc:  # noqa: BLE001
                logger.error("on_message handler raised: %s", exc)

        try:
            self._queue.put_nowait(tick)
        except Exception:
            # Queue full — drop the oldest and keep the freshest tick.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(tick)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Convenience factory
# ─────────────────────────────────────────────────────────────────────────────


def build_default_client(
    symbols: Iterable[str] | None = None,
    on_message: Callable[[VNQuoteTick], None] | None = None,
) -> VNWebSocketClient:
    """Construct a client using the project-wide default config."""

    boards = [
        b.strip().upper()
        for b in (settings.vn_ws_boards or "").split(",")
        if b.strip()
    ] or list(DEFAULT_BOARDS)
    return VNWebSocketClient(
        symbols=symbols or settings.vn_ws_symbols.split(","),
        on_message=on_message,
        boards=boards,
        dead_man_timeout=float(settings.vn_ws_dead_man_seconds),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Manual smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover - manual CLI helper
    import argparse

    parser = argparse.ArgumentParser(
        description="Stream SSI iBoard real-time quotes to stdout."
    )
    parser.add_argument(
        "--symbols", default="FPT,VNM,VCB", help="Comma-separated VN tickers."
    )
    parser.add_argument(
        "--boards", default="MAIN,HNX,UPCOM", help="Comma-separated board IDs."
    )
    parser.add_argument(
        "--duration", type=int, default=30,
        help="Stop after N seconds (0 = run until Ctrl+C).",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    boards = [b.strip().upper() for b in args.boards.split(",") if b.strip()]

    def _print(tick: VNQuoteTick) -> None:
        ts = tick.ts.strftime("%H:%M:%S")
        print(
            f"{ts} {tick.exchange:<6} {tick.symbol:<4} "
            f"price={tick.price:>10,.1f} vol={tick.volume:>10,.0f} "
            f"chg={tick.change:+,.1f} ({tick.change_pct:+.2f}%) "
            f"side={tick.side}"
        )

    client = VNWebSocketClient(
        symbols=symbols, boards=boards, on_message=_print
    )
    client.connect(blocking=False)
    try:
        if args.duration > 0:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
