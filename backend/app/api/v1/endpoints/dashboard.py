"""Dashboard endpoint."""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_dashboard_service, get_db
from app.schemas.common import ok
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/{symbol}")
def get_dashboard(
    symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session | None = Depends(get_db),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict:
    """The dashboard payload for one symbol.

    `start` and `end` narrow the window. They do not change WHICH rows
    the lakehouse holds - they change how much of it travels over the
    wire. The stored history of a ten-year daily ticker is ~121 monthly
    parquet partitions, so a three-month window reads ~3 of them
    instead of all 121.
    """
    return ok(service.build(symbol.upper(), db=db, start=start, end=end))
