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
