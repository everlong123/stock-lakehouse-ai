"""The data quality gate's endpoints: what the lakehouse knows about itself.

WHY THESE ENDPOINTS EXIST
--------------------------
Every other endpoint answers a question about the DATA: what is the price,
what is the forecast, what did the backtest earn. This one answers the
question about the DATA ITSELF: is it clean, and since when.

The answer has to be reachable from the browser, because a quality report
that lives in a terminal is a quality report nobody reads. And it has to be
an endpoint rather than a computed-on-demand value, because the gate costs
a network call per symbol - recomputing it on every page load would be
both slow and pointless.

WHY THE ENDPOINT SERVES A STORED SNAPSHOT
------------------------------------------
The snapshot is written by the cron job, not by the request. Two reasons:

  * the gate is slow enough (a provider round-trip per symbol) that
    running it on demand would make the page unusable;
  * a gate that recomputes on every request would show a DIFFERENT answer
    every time, and a quality signal that flickers is not a signal.

The endpoint also accepts ``?run=true`` for the manual case: run the gate
now, and wait for it. It is off by default because it is an expensive
operation, and an endpoint that anyone can trigger a thousand times an hour
is a denial-of-service vector.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.logging_config import get_logger
from app.schemas.common import ok

logger = get_logger(__name__)

router = APIRouter(prefix="/quality", tags=["quality"])


@router.get("/gate")
def quality_gate(
    run: bool = Query(
        default=False,
        description="Run the gate now instead of serving the stored snapshot.",
    ),
) -> dict:
    """The lakehouse's own quality verdict.

    Returns the stored snapshot by default. The snapshot carries:

    * ``verdict`` - ``passed``, ``warning`` or ``failed``;
    * ``checks`` - one entry per check, each with its own status, how many
      symbols it examined, and the symbols that failed it;
    * ``history`` - the recent verdicts, so the page can show whether the
      data is improving or degrading.

    A check whose status is ``unavailable`` means the check COULD NOT RUN.
    That is never reported as a pass: a gate that says "clean" because it
    could not look at anything is worse than no gate at all.
    """
    from app.services.quality_gate_service import run_and_persist, summary

    if run:
        payload = run_and_persist()
        return ok(payload, message="The quality gate was run on request.")

    return ok(summary())


@router.get("/gate/history")
def quality_gate_history(limit: int = Query(default=30, ge=1, le=100)) -> dict:
    """The recent gate snapshots, newest first."""
    from app.services.quality_gate_service import read_history

    return ok({"history": read_history(limit=limit)})


@router.post("/gate/run")
def run_quality_gate(
    symbols: str | None = Query(
        default=None,
        description="Comma-separated symbols to check. Omit for the whole universe.",
    ),
) -> dict:
    """Run the gate now, and return the fresh snapshot.

    This is the manual counterpart of the cron job. It is a POST because
    it does work that costs minutes on a full universe, and a GET endpoint
    that a browser could trigger by prefetching would be a liability.
    """
    from app.services.quality_gate_service import run_and_persist

    targets = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None
    payload = run_and_persist(symbols=targets)
    return ok(payload, message="The quality gate ran.")
