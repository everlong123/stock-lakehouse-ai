"""Backtesting endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_backtest_service, get_db
from app.schemas.backtesting import BacktestRequest
from app.schemas.common import ok
from app.services.backtest_service import BacktestService

router = APIRouter(prefix="/backtests", tags=["backtesting"])


@router.get("/multi-symbol-report")
def multi_symbol_report(
    strategy: str = Query(default="ma_crossover"),
) -> dict:
    """Return the multi-symbol walk-forward + buy-and-hold report.

    WHY IT IS NOT COMPUTED ON DEMAND
    --------------------------------
    The run replays ~100 symbols over ~37 windows each, which takes
    ~75 seconds of CPU (measured 18/11/2026). Serving that from a
    request handler would tie up a worker for a minute and return a
    timeout to the browser - the exact failure mode the thesis defence
    cannot afford.

    So the report is PRODUCED AHEAD OF TIME and stored, and this
    endpoint only reads it.

    WHERE THE REPORT LIVES
    ----------------------
    In the lakehouse's ``backtests`` layer, which is MinIO in
    production. That layer is the one place the ``scheduler`` container
    (which runs the nightly job) and the ``backend`` container (which
    serves this endpoint) can both reach: they share MySQL and MinIO,
    but they do NOT share the ``data`` volume, so a file written to the
    scheduler's filesystem would be invisible here.

    The nightly job is ``run_scheduled_job.py walk-forward``. It runs the
    SAME service the manual script runs, so the numbers on the page
    cannot drift away from the numbers in the log.

    When no report exists yet, the endpoint says so plainly and gives
    the command that produces one. It never invents numbers.
    """
    from app.services.walk_forward_report_service import (
        LOCAL_REPORT_FILES,
        STRATEGIES,
        read_report,
    )

    if strategy not in STRATEGIES:
        return ok(
            {
                "available": False,
                "reason": (
                    f"Chưa có báo cáo cho chiến lược '{strategy}'. "
                    f"Các chiến lược có sẵn: {', '.join(sorted(STRATEGIES))}."
                ),
            },
            message="No report for this strategy.",
        )

    payload = read_report(strategy)
    if payload is None:
        return ok(
            {
                "available": False,
                "strategy": strategy,
                "reason": (
                    "Chưa có báo cáo đa mã. Lệnh tạo: "
                    "cd backend && .venv/Scripts/python.exe scripts/run_multi_symbol_walkforward.py "
                    f"--per-exchange 8 --strategy {strategy}. "
                    "Lệnh này cũng chạy tự động mỗi tối qua cron job "
                    "'walk-forward'."
                ),
            },
            message="Report not found.",
        )

    payload["available"] = True
    # The strategies the endpoint serves, so the UI can offer exactly the
    # ones that are actually available rather than hard-coding a list.
    payload["available_strategies"] = sorted(STRATEGIES)
    return ok(payload, message="Multi-symbol walk-forward report.")


@router.post("/run")
def run_backtest(
    payload: BacktestRequest,
    db: Session | None = Depends(get_db),
    service: BacktestService = Depends(get_backtest_service),
) -> dict:
    result = service.run(payload.model_dump(), db=db)
    return ok(result, message="Historical backtest finished. This is not live trading.")


@router.get("/history")
def backtest_history(
    symbol: str | None = Query(default=None),
    db: Session | None = Depends(get_db),
    service: BacktestService = Depends(get_backtest_service),
) -> dict:
    return ok(service.history(symbol, db=db))
