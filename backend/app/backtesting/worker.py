"""Child-process entry points for the CPU-bound backtesting jobs.

These functions live in their own module so they can be pickled and sent to
the process pool (see :mod:`app.core.heavy_worker`). They must stay
module-level and side-effect free at import time.

WHY A SEPARATE PROCESS
-----------------------
The walk-forward validator runs the strategy over ~175 rolling windows, and
each window re-computes RSI over the whole training slice. That is pure
pandas work, so it competes for the GIL with the auto-refresh pass that runs
in the same API process. Measured on this box:

    idle process .............. 2.2 s
    refresh running ........... 13.3 s
    real server load .......... 96 s   -> blew the 75 s agent deadline

Running the validator in a child process gives it its own GIL, so it keeps
its speed no matter how busy the parent is.
"""

from __future__ import annotations

from typing import Any


def run_walk_forward_job(
    symbol: str,
    strategy_name: str,
    train_period_days: int = 180,
    test_period_days: int = 30,
    step_days: int = 20,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = 10_000.0,
    transaction_fee: float = 0.001,
    slippage: float = 0.0005,
    parameters: dict | None = None,
) -> dict[str, Any]:
    """Run a walk-forward validation and return the plain-dict result.

    This is the picklable wrapper the process pool calls. The result is a
    dict of plain Python types, so it survives the pickle round-trip
    unchanged.
    """
    from app.backtesting.walk_forward import WalkForwardValidator

    validator = WalkForwardValidator(
        train_period_days=train_period_days,
        test_period_days=test_period_days,
        step_days=step_days,
    )
    return validator.run(
        symbol=symbol,
        strategy_name=strategy_name,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        transaction_fee=transaction_fee,
        slippage=slippage,
        parameters=parameters,
    )


def run_backtest_job(
    symbol: str,
    strategy_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = 10_000.0,
    transaction_fee: float = 0.001,
    slippage: float = 0.0005,
    parameters: dict | None = None,
) -> dict[str, Any]:
    """Run a single backtest and return the plain-dict result."""
    from app.backtesting.engine import BacktestEngine

    return BacktestEngine().run(
        symbol=symbol,
        strategy_name=strategy_name,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        transaction_fee=transaction_fee,
        slippage=slippage,
        parameters=parameters,
    )
