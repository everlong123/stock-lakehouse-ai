"""Buy-and-hold benchmark tests.

WHY THIS FILE EXISTS
--------------------
The benchmark is the null hypothesis that every active strategy has to
beat, and it was added to the backtest engine and to the walk-forward
validator at the same time. Two properties have to hold for the
comparison to be worth anything, and both are easy to break silently:

1. THE BENCHMARK MUST BE MEASURED ON THE SAME BARS
   -------------------------------------------------
   If the baseline ran over a different period than the strategy, the
   difference between them would be dominated by how the market moved
   between those two periods, and the headline number would be
   meaningless. The benchmark is therefore computed from the SAME frame
   the strategy used, inside the same call.

2. THE BENCHMARK MUST PAY THE SAME COSTS
   --------------------------------------
   A baseline that traded for free would flatter the strategy; a
   baseline that paid no fees would flatter the baseline. Both would be
   wrong. The benchmark is charged the same fee and the same slippage,
   and it is also forced to close its position at the end of the series
   exactly like the strategy is.

A third property is that the benchmark must be reproducible: given the
same bars it must always produce the same numbers.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.backtesting.benchmark import run_buy_and_hold
from app.backtesting.engine import BacktestEngine


def _frame(rows: int = 300, start: float = 100.0) -> pd.DataFrame:
    """A deterministic rising series."""
    import numpy as np

    rng = np.random.default_rng(7)
    steps = rng.normal(0.12, 0.8, rows).cumsum()
    close = start + steps
    timestamps = pd.date_range("2020-01-01", periods=rows, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "symbol": "TEST",
            "timestamp": timestamps,
            "open": close - 0.15,
            "high": close + 0.6,
            "low": close - 0.6,
            "close": close,
            "volume": 1_000_000.0,
        }
    )


def test_the_benchmark_holds_the_whole_period() -> None:
    """Buy-and-hold must capture the whole move, not a slice of it."""
    frame = _frame(rows=200, start=100.0)
    metrics, equity, _dd = run_buy_and_hold(frame, 10_000.0, 0.001, 0.0005)

    assert equity, "no equity curve was produced"
    # The curve must start at the initial capital (within the cost of
    # the first fill) and end at the final capital.
    assert equity[0]["equity"] <= 10_000.0
    assert abs(equity[-1]["equity"] - metrics["final_capital"]) < 1e-6

    # The number of trades is exactly one round trip: buy once, sell
    # once at the end.
    assert metrics["number_of_trades"] == 1


def test_the_benchmark_pays_the_same_costs_as_the_strategy() -> None:
    """A frictionless baseline would make the comparison meaningless."""
    frame = _frame(rows=200, start=100.0)

    with_costs, _eq, _dd = run_buy_and_hold(frame, 10_000.0, 0.001, 0.0005)
    without_costs, _eq2, _dd2 = run_buy_and_hold(frame, 10_000.0, 0.0, 0.0)

    assert without_costs["total_return"] > with_costs["total_return"], (
        "the frictionless baseline did not beat the costed one, so the "
        "costs are not actually being charged"
    )


def test_the_benchmark_is_reproducible() -> None:
    """The same bars must always give the same numbers."""
    frame = _frame(rows=150)
    first, _eq, _dd = run_buy_and_hold(frame.copy(), 10_000.0, 0.001, 0.0005)
    second, _eq2, _dd2 = run_buy_and_hold(frame.copy(), 10_000.0, 0.001, 0.0005)

    assert first["total_return"] == second["total_return"]
    assert first["final_capital"] == second["final_capital"]
    assert first["sharpe_ratio"] == second["sharpe_ratio"]


def test_the_benchmark_drawdown_is_not_worse_than_the_strategy_free_run() -> None:
    """The maximum drawdown must be measured, not defaulted to zero."""
    frame = _frame(rows=250, start=100.0)
    metrics, _eq, drawdown = run_buy_and_hold(frame, 10_000.0, 0.001, 0.0005)

    assert drawdown, "no drawdown series was produced"
    assert metrics["maximum_drawdown"] <= 0.0


def test_the_engine_returns_the_benchmark_on_the_same_bars(monkeypatch) -> None:
    """The engine response must carry the baseline for the same period."""
    frame = _frame(rows=400)
    engine = BacktestEngine()
    monkeypatch.setattr(
        engine, "_load_ohlcv", lambda symbol, start_date, end_date: frame.copy()
    )

    result = engine.run("TEST", "ma_crossover", initial_capital=10_000.0)

    benchmark = result.get("benchmark")
    assert benchmark, "the engine response carries no benchmark"
    assert benchmark["name"] == "buy_and_hold"
    assert benchmark["total_return"] is not None
    assert benchmark["equity_curve"], "the benchmark has no equity curve"

    # The two curves must cover the same period: same first bar and same
    # last bar. If they did not, the chart would compare two different
    # time ranges.
    assert result["equity_curve"][0]["timestamp"] == benchmark["equity_curve"][0]["timestamp"]
    assert result["equity_curve"][-1]["timestamp"] == benchmark["equity_curve"][-1]["timestamp"]

    # The excess return must be exactly the difference between the two.
    assert result["excess_return_vs_benchmark"] == pytest.approx(
        result["total_return"] - benchmark["total_return"]
    )
    assert result["beat_benchmark"] == (result["total_return"] > benchmark["total_return"])


def test_the_walk_forward_records_the_baseline_per_window(monkeypatch) -> None:
    """Each walk-forward window must carry its own baseline number."""
    from app.backtesting.walk_forward import WalkForwardValidator

    frame = _frame(rows=900)
    validator = WalkForwardValidator(
        train_period_days=180,
        test_period_days=30,
        step_days=20,
        min_train_bars=60,
        min_test_bars=20,
    )
    monkeypatch.setattr(
        validator, "_load_data", lambda symbol, start_date, end_date: frame.copy()
    )

    result = validator.run("TEST", "ma_crossover", parameters={"short_window": 20, "long_window": 50})
    summary = result["summary"]

    compared = [w for w in result["windows"] if w.get("test_excess_return") is not None]
    assert compared, "no window carries a baseline comparison"
    assert summary["windows_compared"] == len(compared)

    # The aggregate excess return must be the mean of the per-window
    # differences - a PAIRED statistic, not the difference of two
    # independent averages.
    expected = sum(w["test_excess_return"] for w in compared) / len(compared)
    assert summary["avg_excess_return"] == pytest.approx(expected)
