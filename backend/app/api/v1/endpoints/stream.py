"""Streaming REST endpoints — expose Kafka stream cache to the frontend."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.logging_config import get_logger
from app.schemas.common import ok
from app.services.stream_service import (
    get_cache,
    publish_bar,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])


# ── Server-Sent Events (real-time push to the browser) ──────────────────────
# The frontend opens ``EventSource('/api/v1/stream/events')`` and receives a
# JSON-encoded ``StreamBar`` for every bar the cache records. No more polling.

_SSE_HEARTBEAT_SECONDS = 15.0  # keep proxies / browsers from closing idle conns


def _format_sse(data: str, event: str | None = None) -> bytes:
    """Encode one SSE message per the W3C spec (text/event-stream)."""
    chunks: list[str] = []
    if event:
        chunks.append(f"event: {event}\n")
    # Each line of data must be prefixed; JSON is single-line so this is safe.
    for line in data.splitlines() or [""]:
        chunks.append(f"data: {line}\n")
    chunks.append("\n")
    return "".join(chunks).encode("utf-8")


@router.get("/events")
async def stream_events(
    symbol: str | None = Query(
        None,
        min_length=1,
        max_length=10,
        description="Optional symbol filter (e.g. AAPL). Omit to receive all bars.",
    ),
) -> StreamingResponse:
    """Server-Sent Events stream of new bars.

    Events:

    - ``bar`` — payload is a JSON-encoded :class:`StreamBar` for one new bar.
    - ``ping`` — heartbeat sent every ``_SSE_HEARTBEAT_SECONDS`` so reverse
      proxies don't drop the connection. The frontend ignores these.

    On connect we also replay the latest bar per symbol (or the filtered
    symbol) so the UI renders something immediately instead of waiting
    for the next tick.
    """
    cache = get_cache()
    queue_obj = cache.subscribe()
    symbol_filter = symbol.upper() if symbol else None

    async def event_generator():
        try:
            # Replay last known bar per symbol so the page isn't empty
            # when the user opens it between ticks.
            for sym, bar in cache.snapshot().items():
                if symbol_filter and sym != symbol_filter:
                    continue
                payload = json.dumps(bar.as_dict())
                yield _format_sse(payload, event="bar")

            # Initial hello so the browser confirms the stream is alive.
            yield _format_sse(json.dumps({"status": "connected"}), event="hello")

            loop = asyncio.get_running_loop()
            while True:
                # Bridge the thread-safe queue to the asyncio loop without
                # blocking the event loop on a slow consumer.
                try:
                    bar = await loop.run_in_executor(None, queue_obj.get, True, _SSE_HEARTBEAT_SECONDS)
                except Exception:  # queue.Empty — emit heartbeat instead
                    yield _format_sse(json.dumps({"ts": "heartbeat"}), event="ping")
                    continue

                if symbol_filter and bar.symbol != symbol_filter:
                    continue
                yield _format_sse(json.dumps(bar.as_dict()), event="bar")
        except asyncio.CancelledError:
            # Browser closed the connection; normal shutdown path.
            logger.debug("SSE client disconnected (symbol=%s)", symbol_filter)
            raise
        finally:
            cache.unsubscribe(queue_obj)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Disable buffering on nginx/cloudflare so events arrive instantly.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/latest")
async def latest(symbol: str | None = None) -> dict:
    """Return the latest bar for one symbol, or one bar per tracked symbol."""
    cache = get_cache()
    if symbol:
        bar = cache.latest(symbol)
        return ok({"bar": bar.as_dict() if bar else None, "symbol": symbol.upper()})
    snapshot = {sym: bar.as_dict() for sym, bar in cache.snapshot().items()}
    return ok({"bars": snapshot, "stats": cache.stats()})


@router.get("/history")
async def history(
    symbol: str = Query(..., min_length=1, max_length=10),
    limit: int = Query(60, ge=1, le=500),
) -> dict:
    """Return the last ``limit`` bars (rolling window) for ``symbol``."""
    history = get_cache().history(symbol, limit=limit)
    return ok({"symbol": symbol.upper(), "bars": [b.as_dict() for b in history], "count": len(history)})


@router.get("/stats")
async def stats() -> dict:
    """Return cache statistics (used by the Live Stream page header)."""
    return ok(get_cache().stats())


@router.post("/ingest")
async def ingest(payload: dict[str, Any]) -> dict:
    """Manual ingest endpoint. Accepts either a single bar or a list of bars.

    Intended for:
    - curl smoke tests against the live API
    - publisher scripts that want to push bars without spinning up Kafka
    - the Live Stream demo button in the UI

    Body::

        {
          "symbol": "AAPL",
          "bars": [
            {"timestamp": "2026-01-01T00:00:00Z", "open": 100, "high": 101,
             "low": 99, "close": 100.5, "volume": 12345}
          ]
        }
    """
    symbol = str(payload.get("symbol", "")).strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    bars = payload.get("bars")
    if not isinstance(bars, list) or not bars:
        raise HTTPException(status_code=400, detail="bars must be a non-empty list")

    accepted = 0
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        publish_bar(symbol, bar)
        accepted += 1

    return ok({"symbol": symbol, "accepted": accepted})