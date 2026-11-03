"""Backtest application service."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.backtesting.engine import BacktestEngine  # noqa: F401 - re-exported for callers
from app.core.heavy_worker import run_in_process
from app.core.logging_config import get_logger
from app.database.repositories.backtest_repository import BacktestRepository
from app.database.session import check_database_connection
from app.lakehouse.local_storage import LocalStorageBackend

logger = get_logger(__name__)


class BacktestService:
    def run(self, payload: dict[str, Any], db: Session | None = None) -> dict[str, Any]:
        parameters = {
            "short_window": payload.get("short_window", 20),
            "long_window": payload.get("long_window", 50),
            "rsi_period": payload.get("rsi_period", 14),
            "lower_threshold": payload.get("lower_threshold", 30),
            "upper_threshold": payload.get("upper_threshold", 70),
        }
        result = self._run_engine(payload, parameters)
        LocalStorageBackend().write_json(
            "backtests",
            f"{result['symbol']}_{result['strategy']}_latest.json",
            result,
        )
        self._persist(result, db)
        return result

    def _run_engine(self, payload: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
        """Run the backtest engine, in a child process when possible.

        WHY: the engine replays the full history bar by bar, which is pure
        pandas/Python work and therefore GIL-bound. In the API process it
        competed with the auto-refresh pass and a 1-second backtest could
        take a minute. A child process has its own GIL, so it stays fast.
        """
        from app.backtesting.worker import run_backtest_job

        kwargs = {
            "symbol": payload["symbol"],
            "strategy_name": payload["strategy"],
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "initial_capital": payload.get("initial_capital", 10000),
            "transaction_fee": payload.get("transaction_fee", 0.001),
            "slippage": payload.get("slippage", 0.0005),
            "parameters": parameters,
        }

        if os.getenv("HEAVY_WORKER_IN_PROCESS", "0").strip() in ("1", "true", "yes"):
            return run_backtest_job(**kwargs)

        try:
            return run_in_process(run_backtest_job, **kwargs)
        except Exception as exc:  # noqa: BLE001 - fall back to the in-process path
            logger.warning(
                "Backtest child process failed (%s); falling back to in-process run.",
                exc,
            )
            return run_backtest_job(**kwargs)

    def history(self, symbol: str | None = None, db: Session | None = None) -> list[dict[str, Any]]:
        if db is not None and check_database_connection():
            try:
                rows = BacktestRepository(db).list_history(symbol)
                return [
                    {
                        "id": row.id,
                        "symbol": row.symbol,
                        "strategy": row.strategy,
                        "start_date": row.start_date.isoformat() if row.start_date else None,
                        "end_date": row.end_date.isoformat() if row.end_date else None,
                        "initial_capital": row.initial_capital,
                        "final_capital": row.final_capital,
                        "total_return": row.total_return,
                        "win_rate": row.win_rate,
                        "sharpe_ratio": row.sharpe_ratio,
                        "maximum_drawdown": row.maximum_drawdown,
                        "number_of_trades": row.number_of_trades,
                        "profit_factor": row.profit_factor,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                    for row in rows
                ]
            except Exception as exc:
                logger.warning("Unable to read backtest history: %s", exc)
        return []

    def _persist(self, result: dict[str, Any], db: Session | None) -> None:
        if db is None or not check_database_connection():
            return
        try:
            BacktestRepository(db).create(
                {
                    "symbol": result["symbol"],
                    "strategy": result["strategy"],
                    "start_date": _parse(result.get("start_date")),
                    "end_date": _parse(result.get("end_date")),
                    "initial_capital": result["initial_capital"],
                    "final_capital": result["final_capital"],
                    "total_return": result["total_return"],
                    "win_rate": result["win_rate"],
                    "sharpe_ratio": result["sharpe_ratio"],
                    "maximum_drawdown": result["maximum_drawdown"],
                    "number_of_trades": result["number_of_trades"],
                    "profit_factor": result["profit_factor"],
                    "parameters": str(result.get("parameters")),
                }
            )
        except Exception as exc:
            logger.warning("Unable to persist backtest run: %s", exc)


def _parse(value) -> datetime | None:
    if not value:
        return None
    import pandas as pd

    return pd.to_datetime(value, utc=True).to_pydatetime().replace(tzinfo=None)


class WalkForwardService:
    """Service for walk-forward validation."""

    def run(
        self,
        payload: dict[str, Any],
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Run walk-forward validation.

        The validation runs in a CHILD PROCESS, not a thread.

        WHY: it is the single most CPU-bound thing the agent can be asked to
        do - the strategy is replayed over ~175 rolling windows, and each
        window re-computes RSI over the whole training slice. In the API
        process that work competes for the GIL with the auto-refresh pass
        running in the background, and the measured effect was brutal:

            idle API process ...... 2.2 s
            refresh running ....... 13.3 s
            real server load ...... 96 s  -> blew the 75 s agent deadline

        A child process has its own interpreter and its own GIL, so the
        validation keeps its speed no matter how busy the parent is. The
        result is a plain dict, so it survives the pickle round-trip
        unchanged.
        """
        result = self._run_validation(payload)

        # Save result
        LocalStorageBackend().write_json(
            "backtests",
            f"{result['symbol']}_{result['strategy']}_walkforward_latest.json",
            result,
        )

        return result

    def _run_validation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the validation, in a child process when possible."""
        from app.backtesting.worker import run_walk_forward_job

        kwargs = {
            "symbol": payload["symbol"],
            "strategy_name": payload.get("strategy", "ma_crossover"),
            "train_period_days": payload.get("train_period_days", 180),
            "test_period_days": payload.get("test_period_days", 30),
            "step_days": payload.get("step_days", 20),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "initial_capital": payload.get("initial_capital", 10000),
            "transaction_fee": payload.get("transaction_fee", 0.001),
            "slippage": payload.get("slippage", 0.0005),
            "parameters": payload.get("parameters"),
        }

        if os.getenv("HEAVY_WORKER_IN_PROCESS", "0").strip() in ("1", "true", "yes"):
            # Escape hatch for debugging: run in this process.
            return run_walk_forward_job(**kwargs)

        try:
            return run_in_process(run_walk_forward_job, **kwargs)
        except Exception as exc:  # noqa: BLE001 - fall back to the in-process path
            logger.warning(
                "Walk-forward child process failed (%s); falling back to in-process run.",
                exc,
            )
            return run_walk_forward_job(**kwargs)
