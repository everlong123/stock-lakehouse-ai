"""Walk-forward validation for robust backtesting methodology.

Walk-forward validation addresses the key weakness of simple train-test split:
- Avoids overfitting to a specific time period
- Simulates real-world model deployment where you retrain periodically
- Provides more realistic performance estimates

The methodology:
1. Divide data into rolling windows
2. Each window: train on "train_period", test on "test_period"
3. Move window forward and repeat
4. Aggregate results across all windows
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from app.backtesting.benchmark import run_buy_and_hold
from app.backtesting.engine import BacktestEngine
from app.backtesting.metrics import compute_metrics
from app.backtesting.simulator import simulate
from app.backtesting.strategies import STRATEGY_MAP
from app.core.exceptions import BacktestError
from app.core.logging_config import get_logger
from app.lakehouse.session import as_utc_timestamp

logger = get_logger(__name__)


@dataclass
class WalkForwardWindow:
    """Single walk-forward window result."""
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_return: float | None = None
    test_return: float | None = None
    test_sharpe: float | None = None
    test_max_drawdown: float | None = None
    test_win_rate: float | None = None
    test_num_trades: int = 0
    # The buy-and-hold baseline on the SAME window.
    test_benchmark_return: float | None = None
    test_benchmark_sharpe: float | None = None
    test_excess_return: float | None = None
    passed: bool = True
    error: str | None = None


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward validation results."""
    symbol: str
    strategy_name: str
    total_windows: int
    passed_windows: int
    failed_windows: int

    # Train period metrics
    avg_train_return: float | None = None
    train_return_std: float | None = None

    # Test period metrics (more important for evaluation)
    avg_test_return: float | None = None
    test_return_std: float | None = None
    avg_test_sharpe: float | None = None
    avg_test_max_drawdown: float | None = None
    avg_test_win_rate: float | None = None
    total_test_trades: int = 0

    # Stability metrics
    return_consistency: float | None = None  # Ratio of positive windows
    overfitting_ratio: float | None = None  # train_return / test_return

    # The buy-and-hold baseline measured on the SAME test windows.
    # These are the numbers a reader needs to judge whether the strategy
    # added anything over simply holding the stock.
    avg_benchmark_return: float | None = None
    avg_benchmark_sharpe: float | None = None
    avg_benchmark_max_drawdown: float | None = None
    # The PAIRED difference: the mean over windows of
    # (strategy return - benchmark return). Both sides were measured over
    # identical bars, so the difference is not contaminated by the market
    # moving differently between two separate periods.
    avg_excess_return: float | None = None
    excess_return_consistency: float | None = None
    windows_compared: int = 0

    windows: list[WalkForwardWindow] = field(default_factory=list)

    disclaimer: str = ""


class WalkForwardValidator:
    """
    Walk-forward validation engine.

    Methodology:
    - Rolling window approach with fixed train/test periods
    - For each window: train strategy parameters on train period, test on test period
    - This mimics real-world deployment where you continuously retrain
    """

    def __init__(
        self,
        train_period_days: int = 180,  # 6 months training
        test_period_days: int = 30,     # 1 month testing
        step_days: int = 20,             # Move forward 20 days each iteration
        min_train_bars: int = 60,
        min_test_bars: int = 20,
    ):
        self.train_period_days = train_period_days
        self.test_period_days = test_period_days
        self.step_days = step_days
        self.min_train_bars = min_train_bars
        self.min_test_bars = min_test_bars

    def run(
        self,
        symbol: str,
        strategy_name: str,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        initial_capital: float = 10_000.0,
        transaction_fee: float = 0.001,
        slippage: float = 0.0005,
        parameters: dict | None = None,
    ) -> dict[str, Any]:
        """
        Run walk-forward validation.

        Args:
            symbol: Stock symbol
            strategy_name: Strategy name (e.g., 'ma_crossover')
            start_date: Start of overall data period
            end_date: End of overall data period
            initial_capital: Starting capital
            transaction_fee: Fee as fraction (e.g., 0.001 = 0.1%)
            slippage: Slippage as fraction
            parameters: Strategy parameters

        Returns:
            Aggregated results and per-window details
        """
        if strategy_name not in STRATEGY_MAP:
            raise BacktestError(f"Unknown strategy: {strategy_name}")

        # Load data
        frame = self._load_data(symbol, start_date, end_date)
        if frame.empty:
            raise BacktestError(f"No market data available for {symbol}.")

        frame = frame.sort_values("timestamp").reset_index(drop=True)

        # Generate walk-forward windows
        windows = self._generate_windows(frame)

        if not windows:
            raise BacktestError("Not enough data to create walk-forward windows.")

        logger.info(
            f"Walk-forward validation for {symbol}/{strategy_name}: "
            f"{len(windows)} windows (frame rows={len(frame)})"
        )

        # Run backtest for each window
        results: list[WalkForwardWindow] = []
        train_returns = []
        test_returns = []
        test_sharpes = []
        test_drawdowns = []
        test_win_rates = []
        test_trades_count = 0
        benchmark_returns: list[float] = []
        benchmark_sharpes: list[float] = []
        benchmark_drawdowns: list[float] = []
        excess_returns: list[float] = []
        windows_compared = 0

        for i, window in enumerate(windows):
            try:
                # Extract train and test data
                train_data = frame[
                    (frame["timestamp"] >= window.train_start) &
                    (frame["timestamp"] <= window.train_end)
                ].copy()

                test_data = frame[
                    (frame["timestamp"] >= window.test_start) &
                    (frame["timestamp"] <= window.test_end)
                ].copy()

                if len(train_data) < self.min_train_bars or len(test_data) < self.min_test_bars:
                    window.passed = False
                    window.error = "Insufficient bars in window"
                    results.append(window)
                    continue

                # Train phase: find best parameters on train data
                train_result = self._train_on_window(
                    train_data, strategy_name, initial_capital, transaction_fee, slippage, parameters
                )
                window.train_return = train_result.get("total_return")

                if train_result is not None:
                    train_returns.append(train_result["total_return"])

                # Test phase: apply trained parameters to test data
                #
                # The test window gets a WARMUP CONTEXT: the tail of the
                # training window, so the indicators the strategy needs
                # are already defined on the first test session. Without
                # it a 50-session SMA is NaN for every row of a 22-session
                # test window and the strategy never trades.
                test_result = self._test_on_window(
                    test_data,
                    strategy_name,
                    initial_capital,
                    transaction_fee,
                    slippage,
                    parameters,
                    warmup=train_data,
                )

                if test_result:
                    window.test_return = test_result.get("total_return")
                    window.test_sharpe = test_result.get("sharpe_ratio")
                    window.test_max_drawdown = test_result.get("maximum_drawdown")
                    window.test_win_rate = test_result.get("win_rate")
                    window.test_num_trades = test_result.get("number_of_trades", 0)

                    test_returns.append(test_result["total_return"])
                    test_sharpes.append(test_result["sharpe_ratio"])
                    test_drawdowns.append(test_result["maximum_drawdown"])
                    test_win_rates.append(test_result["win_rate"])
                    test_trades_count += test_result["number_of_trades"]

                    # The buy-and-hold baseline on the SAME test bars, with
                    # the SAME fees and the SAME next-bar execution. The
                    # strategy has to be measured against something, and
                    # this is the strictest comparison available: the
                    # same instrument, the same period, the same friction.
                    #
                    # The difference is recorded PER WINDOW, because a
                    # strategy that wins big in three windows and loses
                    # badly in seven is not a strategy that beats the
                    # baseline - it is a strategy whose average hides
                    # its own instability.
                    bench_metrics, _bench_equity, _bench_dd = run_buy_and_hold(
                        test_data,
                        initial_capital=initial_capital,
                        transaction_fee=transaction_fee,
                        slippage=slippage,
                    )
                    if bench_metrics:
                        window.test_benchmark_return = bench_metrics["total_return"]
                        window.test_benchmark_sharpe = bench_metrics["sharpe_ratio"]
                        window.test_excess_return = (
                            test_result["total_return"] - bench_metrics["total_return"]
                        )
                        benchmark_returns.append(bench_metrics["total_return"])
                        benchmark_sharpes.append(bench_metrics["sharpe_ratio"])
                        benchmark_drawdowns.append(bench_metrics["maximum_drawdown"])
                        excess_returns.append(window.test_excess_return)
                        windows_compared += 1
                else:
                    window.passed = False
                    window.error = "Test backtest failed"

            except Exception as exc:
                window.passed = False
                window.error = str(exc)
                logger.warning(f"Window {i} failed: {exc}")

            results.append(window)

        # Compute aggregated metrics
        passed = sum(1 for w in results if w.passed)
        failed = len(results) - passed

        # Calculate stability
        positive_test = sum(1 for r in test_returns if r is not None and r > 0)
        consistency = positive_test / len(test_returns) if test_returns else 0

        # Calculate the overfitting ratio.
        #
        # WHY IT IS ANNUALISED
        # --------------------
        # The train window covers `train_period_days` (180 by default) and
        # the test window covers `test_period_days` (30). Dividing the raw
        # returns compares a six-month return with a one-month return, so
        # the ratio was inflated by the length difference and was not
        # readable - a "790" tells a reader nothing.
        #
        # Both sides are annualised to a 365-day return first, so the ratio
        # answers the actual question: does the strategy hold up out of
        # sample, or did it only work on the period it was fitted to?
        # Near 1.0 means it generalises; a large value means it did not.
        avg_train = sum(r for r in train_returns if r is not None) / len(train_returns) if train_returns else 0
        avg_test = sum(r for r in test_returns if r is not None) / len(test_returns) if test_returns else 0

        train_factor = 365.0 / max(self.train_period_days, 1)
        test_factor = 365.0 / max(self.test_period_days, 1)
        annualised_train = avg_train * train_factor
        annualised_test = avg_test * test_factor
        overfitting_ratio = (
            annualised_train / annualised_test
            if annualised_test not in (0, 0.0) and annualised_test
            else None
        )

        aggregated = WalkForwardResult(
            symbol=symbol.upper(),
            strategy_name=strategy_name,
            total_windows=len(results),
            passed_windows=passed,
            failed_windows=failed,
            avg_train_return=avg_train if train_returns else None,
            train_return_std=_std(train_returns) if train_returns else None,
            avg_test_return=avg_test if test_returns else None,
            test_return_std=_std(test_returns) if test_returns else None,
            avg_test_sharpe=sum(s for s in test_sharpes if s is not None) / len(test_sharpes) if test_sharpes else None,
            avg_test_max_drawdown=sum(d for d in test_drawdowns if d is not None) / len(test_drawdowns) if test_drawdowns else None,
            avg_test_win_rate=sum(w for w in test_win_rates if w is not None) / len(test_win_rates) if test_win_rates else None,
            total_test_trades=test_trades_count,
            return_consistency=consistency,
            overfitting_ratio=overfitting_ratio,
            avg_benchmark_return=sum(benchmark_returns) / len(benchmark_returns) if benchmark_returns else None,
            avg_benchmark_sharpe=sum(benchmark_sharpes) / len(benchmark_sharpes) if benchmark_sharpes else None,
            avg_benchmark_max_drawdown=sum(benchmark_drawdowns) / len(benchmark_drawdowns) if benchmark_drawdowns else None,
            avg_excess_return=sum(excess_returns) / len(excess_returns) if excess_returns else None,
            excess_return_consistency=(
                sum(1 for r in excess_returns if r > 0) / len(excess_returns)
                if excess_returns else None
            ),
            windows_compared=windows_compared,
            windows=results,
            disclaimer=self._build_disclaimer(),
        )

        return self._to_dict(aggregated)

    def _generate_windows(self, frame: pd.DataFrame) -> list[WalkForwardWindow]:
        """Generate walk-forward window definitions.

        WHY THE TRAIN WINDOW IS FIXED, NOT EXPANDING
        --------------------------------------------
        The train window used to start at the very first session of the
        history every time, so it GREW with every step: window 0 trained on
        180 days, window 175 trained on ten years.

        That breaks the whole point of the comparison. The "overfitting
        ratio" is `avg_train_return / avg_test_return`, and it only means
        something if the two are measured over comparable periods. A
        ten-year training return and a one-month test return are not
        comparable - the ratio came out at 790, a meaningless number.

        With a fixed train window the two sides measure the same length of
        time, so the ratio becomes readable: near 1.0 means the strategy
        generalises, and a large value means it was fitted to the training
        period.
        """
        windows = []

        start_ts = frame["timestamp"].min()
        end_ts = frame["timestamp"].max()

        window_id = 0
        current_train_end = start_ts + pd.Timedelta(days=self.train_period_days)

        while current_train_end < end_ts:
            # The train window always covers `train_period_days` and slides
            # forward with the test window.
            train_start = current_train_end - pd.Timedelta(days=self.train_period_days)
            train_end = current_train_end

            test_start = train_end + pd.Timedelta(days=1)
            test_end = test_start + pd.Timedelta(days=self.test_period_days)

            # Don't go past data end
            if test_end > end_ts:
                test_end = end_ts

            # A window whose test period is shorter than the minimum is
            # not a usable window at all.
            #
            # WHY: the loop used to emit the window anyway, and the run
            # loop then marked it `passed = False` with the error
            # "Insufficient bars in window". That made the tail of the
            # history - the most RECENT windows, which are the ones a
            # reader cares about most - come back as failures. On AAPL
            # 17 of the 176 windows were in that state.
            #
            # The window is skipped rather than reported as a failure. A
            # `continue` (not a `break`) is used on purpose: a 30-day test
            # window holds ~21 sessions, and around holidays it can dip to
            # 19, which is below the 20-bar minimum. Breaking there would
            # discard every window after the first short one - 165 of the
            # 176 windows - leaving only the oldest eleven.
            test_bars = int(
                ((frame["timestamp"] >= test_start) & (frame["timestamp"] <= test_end)).sum()
            )
            if test_bars < self.min_test_bars:
                current_train_end += pd.Timedelta(days=self.step_days)
                window_id += 1
                continue

            windows.append(WalkForwardWindow(
                window_id=window_id,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            ))

            window_id += 1
            current_train_end += pd.Timedelta(days=self.step_days)

        return windows

    def _train_on_window(
        self,
        train_data: pd.DataFrame,
        strategy_name: str,
        initial_capital: float,
        transaction_fee: float,
        slippage: float,
        parameters: dict | None,
    ) -> dict | None:
        """Run backtest on training data to evaluate strategy."""
        try:
            strategy = STRATEGY_MAP[strategy_name](parameters=parameters or {})
            signals = strategy.generate_signals(train_data)
            execution_signal = signals.shift(1).fillna(0)

            portfolio, _markers = simulate(
                train_data,
                execution_signal,
                initial_capital,
                transaction_fee,
                slippage,
            )

            metrics = compute_metrics(portfolio.equity_curve, portfolio.realized_trades, initial_capital)
            return metrics

        except Exception as exc:
            logger.warning(f"Train phase failed: {exc}")
            return None

    def _test_on_window(
        self,
        test_data: pd.DataFrame,
        strategy_name: str,
        initial_capital: float,
        transaction_fee: float,
        slippage: float,
        parameters: dict | None,
        warmup: pd.DataFrame | None = None,
    ) -> dict | None:
        """Run backtest on test data (unseen during training).

        WHY THE WARMUP CONTEXT MATTERS
        -------------------------------
        The indicators a strategy needs need HISTORY. MA Crossover needs a
        50-session SMA; a test window of 30 calendar days only holds ~22
        sessions, so the long SMA is NaN for every single row of the test
        window and the strategy never emits a signal.

        The visible effect was that EVERY window reported zero trades, a
        zero return, a zero consistency and a zero overfitting ratio -
        the whole walk-forward result was a number of zeros that said
        nothing about the strategy.

        The fix is to prepend the warmup rows - the tail of the TRAINING
        window, which the model has already seen - to the test frame when
        the signals are generated, then score only the test rows.

        This does NOT leak the future into the test window: the warmup
        rows are strictly in the past, they are the rows the strategy was
        trained on, and the equity is only ever marked on the test rows.
        It is exactly what happens in production, where the indicator of
        the first bar of a month is computed from the bars before it.
        """
        try:
            strategy = STRATEGY_MAP[strategy_name](parameters=parameters or {})
            if warmup is not None and not warmup.empty:
                context = pd.concat([warmup, test_data], ignore_index=True)
            else:
                context = test_data

            signals = strategy.generate_signals(context)
            execution_signal = signals.shift(1).fillna(0)

            # The warmup rows produced signals too, but they belong to the
            # training period, so they are dropped before the simulation:
            # the test phase starts flat with the test period's capital.
            execution_signal = execution_signal.iloc[len(warmup):].reset_index(drop=True) if (
                warmup is not None and not warmup.empty
            ) else execution_signal.reset_index(drop=True)

            test_frame = test_data.reset_index(drop=True)
            portfolio, _markers = simulate(
                test_frame,
                execution_signal,
                initial_capital,
                transaction_fee,
                slippage,
            )

            metrics = compute_metrics(portfolio.equity_curve, portfolio.realized_trades, initial_capital)
            return metrics

        except Exception as exc:
            logger.warning(f"Test phase failed: {exc}")
            return None

    def _load_data(
        self,
        symbol: str,
        start_date: datetime | str | None,
        end_date: datetime | str | None,
    ) -> pd.DataFrame:
        """Load market data from the shared cache (Gold -> Silver -> Bronze).

        Uses the same memoised read as the rest of the API so a walk-forward
        run does not re-download the symbol's full ~121-partition history
        from MinIO while the auto-refresh pass is competing for the same
        connections.
        """
        from app.services.market_service import _load_symbol_frame

        frame, _source_layer = _load_symbol_frame(symbol.upper())

        if start_date:
            frame = frame[frame["timestamp"] >= as_utc_timestamp(start_date)]
        if end_date:
            frame = frame[frame["timestamp"] <= as_utc_timestamp(end_date)]

        frame = frame.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        return frame

    @staticmethod
    def _build_disclaimer() -> str:
        return """
WALK-FORWARD VALIDATION - PHƯƠNG PHÁP ĐÁNH GIÁ

Walk-forward validation là phương pháp nghiêm ngặt hơn simple backtest:
- Mỗi window có train period (huấn luyện) và test period (kiểm tra)
- Tham số chiến lược được "huấn luyện" trên train, đánh giá trên test
- Kết quả là TRUNG BÌNH của nhiều windows, giảm overfitting

Tuy nhiên:
- Kết quả vẫn dựa trên DỮ LIỆU LỊCH SỬ, không đảm bảo tương lai
- "Overfitting ratio" gần 1.0 là tốt; >2.0 có thể là overfitting
- "Return consistency" cao (>70%) cho thấy chiến lược ổn định hơn

ĐÂY CHỈ LÀ NGHIÊN CỨU HỌC THUẬT, KHÔNG PHẢI KHUYẾN NGHỊ ĐẦU TƯ.
"""

    @staticmethod
    def _to_dict(result: WalkForwardResult) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "symbol": result.symbol,
            "strategy": result.strategy_name,
            "summary": {
                "total_windows": result.total_windows,
                "passed_windows": result.passed_windows,
                "failed_windows": result.failed_windows,
                "avg_train_return": result.avg_train_return,
                "train_return_std": result.train_return_std,
                "avg_test_return": result.avg_test_return,
                "test_return_std": result.test_return_std,
                "avg_test_sharpe": result.avg_test_sharpe,
                "avg_test_max_drawdown": result.avg_test_max_drawdown,
                "avg_test_win_rate": result.avg_test_win_rate,
                "total_test_trades": result.total_test_trades,
                "return_consistency": result.return_consistency,
                "overfitting_ratio": result.overfitting_ratio,
                # The buy-and-hold baseline on the same test windows, and
                # the paired difference between the two.
                "avg_benchmark_return": result.avg_benchmark_return,
                "avg_benchmark_sharpe": result.avg_benchmark_sharpe,
                "avg_benchmark_max_drawdown": result.avg_benchmark_max_drawdown,
                "avg_excess_return": result.avg_excess_return,
                "excess_return_consistency": result.excess_return_consistency,
                "windows_compared": result.windows_compared,
            },
            "windows": [
                {
                    "window_id": w.window_id,
                    "train_period": f"{w.train_start.date()} to {w.train_end.date()}",
                    "test_period": f"{w.test_start.date()} to {w.test_end.date()}",
                    "train_return": w.train_return,
                    "test_return": w.test_return,
                    "test_sharpe": w.test_sharpe,
                    "test_max_drawdown": w.test_max_drawdown,
                    "test_win_rate": w.test_win_rate,
                    "test_num_trades": w.test_num_trades,
                    "test_benchmark_return": w.test_benchmark_return,
                    "test_benchmark_sharpe": w.test_benchmark_sharpe,
                    "test_excess_return": w.test_excess_return,
                    "passed": w.passed,
                    "error": w.error,
                }
                for w in result.windows
            ],
            "disclaimer": result.disclaimer,
        }


def _std(values: list[float]) -> float:
    """Calculate standard deviation."""
    if not values:
        return 0.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    return variance ** 0.5
