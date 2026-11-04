"""Admin endpoints: auto-refresh service status + manual trigger."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.core.logging_config import get_logger
from app.schemas.common import ok
from app.services.auto_refresh import get_service

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/auto-refresh", tags=["admin"])


@router.get("/status")
def get_status() -> dict:
    """Return current status + last summary of the auto-refresh service."""
    svc = get_service()
    return ok(
        {
            "last_run_at": svc.last_run_at.isoformat() if svc.last_run_at else None,
            "last_summary": svc.last_summary,
        }
    )


@router.post("/run")
def trigger_run(background_tasks: BackgroundTasks, symbols: Optional[str] = Query(default=None)) -> dict:
    """Trigger a refresh pass.

    - symbols: optional comma-separated list (e.g. "AAPL,MSFT"). If None, refreshes
      the configured default symbol set.
    - The run is queued as a background task so the HTTP response returns immediately.
    """
    svc = get_service()
    target = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None

    def _job():
        try:
            svc.run_once(target)
        except Exception as exc:
            logger.exception("Manual auto-refresh run failed: %s", exc)

    background_tasks.add_task(_job)
    return ok({"queued": True, "symbols": target or "default"})


@router.post("/cache/invalidate")
def invalidate_cache(symbols: Optional[str] = Query(default=None)) -> dict:
    """Drop the API's memoised symbol frames.

    WHY THIS EXISTS
    ---------------
    ``MarketService`` caches each symbol's frame in memory for 15 minutes so
    that browsing many symbols does not re-download the whole lakehouse from
    MinIO every time. That cache is a correctness hazard for anything that
    WRITES to the lakehouse from outside the API process: a backfill or a
    re-ingest run as a standalone script updates Bronze/Silver/Gold, but the
    API keeps serving the pre-write frame until the TTL expires.

    Concretely, on 2026-11-03 a provider-restatement re-ingest corrected
    ``AIR.PA`` in storage, and the API still returned the old close for
    2026-10-19 - a verification run then reported a mismatch that did not
    exist in storage. This endpoint makes the write visible immediately.

    - symbols: optional comma-separated list. If omitted, the ENTIRE cache is
      cleared.
    """
    from app.services.market_service import clear_symbol_cache, invalidate_symbol_cache

    if symbols:
        targets = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        for symbol in targets:
            invalidate_symbol_cache(symbol)
        logger.info("Admin: invalidated cache for %s", ", ".join(targets))
        return ok({"invalidated": targets})

    clear_symbol_cache()
    logger.info("Admin: cleared the whole symbol cache")
    return ok({"invalidated": "all"})
