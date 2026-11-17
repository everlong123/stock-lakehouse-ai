"""Backtesting endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_backtest_service, get_db
from app.schemas.backtesting import BacktestRequest
from app.schemas.common import ok
from app.services.backtest_service import BacktestService

router = APIRouter(prefix="/backtests", tags=["backtesting"])

# The multi-symbol walk-forward report is produced OFFLINE by
# ``backend/scripts/run_multi_symbol_walkforward.py`` and written to
# ``backend/data/multi_symbol_walkforward.json``.
#
# WHY it is not computed on demand: the run replays ~100 symbols over
# ~37 windows each, which takes ~90 seconds of CPU. Serving that from a
# request handler would tie up a worker for a minute and return a
# timeout to the browser - the exact failure mode the thesis defence
# cannot afford. The report is therefore a FILE that the endpoint
# reads, and the endpoint says plainly when the file is missing instead
# of inventing numbers.
_REPORT_DIR = Path(__file__).resolve().parents[4] / "data"
_REPORT_FILES = {
    "ma_crossover": "multi_symbol_walkforward.json",
    "rsi_strategy": "multi_symbol_walkforward_rsi.json",
}


@router.get("/multi-symbol-report")
def multi_symbol_report(
    strategy: str = Query(default="ma_crossover"),
) -> dict:
    """Return the multi-symbol walk-forward + buy-and-hold report."""
    import json

    filename = _REPORT_FILES.get(strategy)
    if filename is None:
        return ok(
            {
                "available": False,
                "reason": (
                    f"Chưa có báo cáo cho chiến lược '{strategy}'. "
                    f"Các chiến lược có sẵn: {', '.join(sorted(_REPORT_FILES))}."
                ),
            },
            message="No report for this strategy.",
        )

    path = _REPORT_DIR / filename
    if not path.exists():
        return ok(
            {
                "available": False,
                "strategy": strategy,
                "reason": (
                    "Chưa chạy báo cáo đa mã. Chạy: "
                    f"cd backend && .venv/Scripts/python.exe scripts/run_multi_symbol_walkforward.py "
                    f"--per-exchange 8 --strategy {strategy}"
                ),
            },
            message="Report file not found.",
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return ok(
            {"available": False, "strategy": strategy, "reason": f"Không đọc được file báo cáo: {exc}"},
            message="Unreadable report file.",
        )

    payload["available"] = True
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
