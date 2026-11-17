"""Event-driven research backtest engine with next-bar execution."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.backtesting.benchmark import run_buy_and_hold
from app.backtesting.metrics import compute_metrics, drawdown_series
from app.backtesting.simulator import simulate
from app.backtesting.strategies import STRATEGY_MAP
from app.core.exceptions import BacktestError
from app.core.logging_config import get_logger
from app.lakehouse.session import as_utc_timestamp

logger = get_logger(__name__)


class BacktestEngine:
    """
    Signal on close of bar t, execute at open (fallback close) of bar t+1.
    This avoids look-ahead bias.
    """

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
    ) -> dict:
        if strategy_name not in STRATEGY_MAP:
            raise BacktestError(f"Unknown strategy: {strategy_name}")
        if initial_capital <= 0:
            raise BacktestError("initial_capital must be positive.")
        frame = self._load_ohlcv(symbol, start_date, end_date)
        strategy = STRATEGY_MAP[strategy_name](parameters=parameters or {})
        signals = strategy.generate_signals(frame)
        # Shift execution by one bar: act on the next open/close.
        execution_signal = signals.shift(1).fillna(0)

        portfolio, markers = simulate(
            frame,
            execution_signal,
            initial_capital,
            transaction_fee,
            slippage,
        )

        metrics = compute_metrics(portfolio.equity_curve, portfolio.realized_trades, initial_capital)

        # The buy-and-hold benchmark on the SAME bars, with the SAME fees
        # and the SAME next-bar execution convention. Without it the
        # strategy's return has nothing to be measured against.
        bench_metrics, bench_equity, bench_drawdown = run_buy_and_hold(
            frame,
            initial_capital=initial_capital,
            transaction_fee=transaction_fee,
            slippage=slippage,
        )

        result = {
            "symbol": symbol.upper(),
            "strategy": strategy_name,
            "start_date": str(frame["timestamp"].iloc[0]),
            "end_date": str(frame["timestamp"].iloc[-1]),
            "initial_capital": initial_capital,
            "final_capital": metrics["final_capital"],
            "total_return": metrics["total_return"],
            "win_rate": metrics["win_rate"],
            "sharpe_ratio": metrics["sharpe_ratio"],
            "maximum_drawdown": metrics["maximum_drawdown"],
            "number_of_trades": metrics["number_of_trades"],
            "profit_factor": metrics["profit_factor"],
            "parameters": {
                **(parameters or {}),
                "transaction_fee": transaction_fee,
                "slippage": slippage,
            },
            "equity_curve": [
                {
                    "timestamp": str(point["timestamp"]),
                    "equity": float(point["equity"]),
                    "price": float(point["price"]),
                }
                for point in portfolio.equity_curve
            ],
            "drawdown": [
                {"timestamp": str(point["timestamp"]), "drawdown": float(point["drawdown"])}
                for point in drawdown_series(portfolio.equity_curve)
            ],
            "trades": [
                {
                    "entry_time": str(trade.entry_time),
                    "exit_time": str(trade.exit_time),
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "quantity": trade.quantity,
                    "pnl": trade.pnl,
                    "return_pct": trade.return_pct,
                    # Both the entry and the exit fee. The PnL above is
                    # already net of them.
                    "fees": trade.fees,
                }
                for trade in portfolio.realized_trades
            ],
            "markers": markers,
            # The baseline the strategy has to beat. The UI draws it on
            # the same axis as the strategy's equity curve.
            "benchmark": {
                "name": "buy_and_hold",
                "total_return": bench_metrics.get("total_return"),
                "sharpe_ratio": bench_metrics.get("sharpe_ratio"),
                "maximum_drawdown": bench_metrics.get("maximum_drawdown"),
                "final_capital": bench_metrics.get("final_capital"),
                "equity_curve": bench_equity,
                "drawdown": bench_drawdown,
            },
            # The two headline comparisons, so a reader does not have to
            # subtract the numbers by hand.
            "excess_return_vs_benchmark": (
                metrics["total_return"] - bench_metrics["total_return"]
                if bench_metrics else None
            ),
            "beat_benchmark": (
                metrics["total_return"] > bench_metrics["total_return"]
                if bench_metrics else None
            ),
            "disclaimer": (
                "Backtesting evaluates historical hypothetical performance only. "
                "It does not prove that a strategy will be profitable in the future."
            ),
        }
        logger.info(
            "Backtest %s %s return=%.4f trades=%s",
            symbol,
            strategy_name,
            metrics["total_return"],
            metrics["number_of_trades"],
        )
        return result

    def _load_ohlcv(
        self,
        symbol: str,
        start_date: datetime | str | None,
        end_date: datetime | str | None,
    ) -> pd.DataFrame:
        # Read through the shared market-service cache instead of going
        # straight to the lakehouse.
        #
        # WHY: a long-history symbol is split into ~121 monthly parquet
        # partitions. Reading them straight from MinIO on every backtest
        # meant a full re-download of the symbol's entire history, and while
        # the auto-refresh pass was rebuilding the same layers those reads
        # queued behind the refresh's own traffic. Measured on this box: the
        # same backtest took 1.2s standalone and 153s through the API, which
        # blew past the frontend's 90s timeout.
        #
        # The market service already caches a symbol's frame (LRU + TTL) and
        # the auto-refresh invalidates the entry for a symbol right after it
        # rewrites that symbol, so a backtest still sees fresh data - it just
        # does not re-download the whole history for every request.
        from app.services.market_service import _load_symbol_frame

        frame, _source_layer = _load_symbol_frame(symbol.upper())
        if frame.empty:
            raise BacktestError(
                f"No market data available for {symbol}. Run the lakehouse pipeline first "
                f"(POST /api/v1/pipeline/run or wait for auto-refresh on startup)."
            )
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        if start_date:
            frame = frame[frame["timestamp"] >= as_utc_timestamp(start_date)]
        if end_date:
            frame = frame[frame["timestamp"] <= as_utc_timestamp(end_date)]
        frame = frame.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        if len(frame) < 60:
            raise BacktestError("Need at least 60 bars to backtest this strategy.")
        return frame
