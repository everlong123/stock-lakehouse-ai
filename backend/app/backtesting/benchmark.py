"""Buy-and-hold benchmark - the null hypothesis every strategy must beat.

WHY A SHARED MODULE
-------------------
The benchmark appears in two places: the per-symbol backtest response
(the UI draws it next to the strategy's equity curve) and the
multi-symbol walk-forward report (the distribution of strategy results
against the distribution of benchmark results). If the two computed it
separately they would drift, and the headline number - "did the strategy
beat buy-and-hold?" - would be a comparison between two different
definitions. So there is one implementation here and both callers use
it.

WHY BUY-AND-HOLD AND NOT A MARKET INDEX
----------------------------------------
An index (SPX, VN-Index) is a different asset with different risk and
different currency. Buy-and-hold of THE SAME symbol on THE SAME bars is
the strictest comparison available: same instrument, same period, same
friction, same execution convention. It answers "was the timing better
than just holding?", which is the only question the strategy actually
claims to answer.

FAIRNESS OF THE COMPARISON
--------------------------
The benchmark pays the SAME costs as the strategy:
  * one entry fee and one exit fee, at the same rates,
  * the same slippage on both the buy and the sell,
  * execution at the next bar's open, exactly like the strategy.

A benchmark that was allowed free fills would flatter the strategy, and
a benchmark that paid no fees would flatter the baseline. Both would be
wrong, so both are charged.
"""

from __future__ import annotations

import pandas as pd

from app.backtesting.metrics import compute_metrics
from app.backtesting.simulator import simulate


def buy_and_hold_signal(frame: pd.DataFrame) -> pd.Series:
    """Signal series that buys on the first bar and sells on the last.

    The signal is shifted by one bar by the caller, so the entry happens
    on the SECOND bar's open and the exit on the bar after the last
    signal. The forced close at the end of the series is handled by
    ``simulate``, which closes any open position on the final close.
    """
    signals = pd.Series(0.0, index=frame.index, dtype=float)
    if len(frame) == 0:
        return signals
    signals.iloc[0] = 1.0
    if len(frame) > 1:
        signals.iloc[-1] = -1.0
    return signals


def run_buy_and_hold(
    frame: pd.DataFrame,
    initial_capital: float = 10_000.0,
    transaction_fee: float = 0.001,
    slippage: float = 0.0005,
) -> tuple[dict, list[dict], list[dict]]:
    """Run buy-and-hold over ``frame``.

    Returns:
        ``(metrics, equity_curve, drawdown)`` - the same shapes the
        backtest engine returns for the strategy, so the UI can render
        the two curves with one code path.
    """
    from app.backtesting.metrics import drawdown_series

    if frame.empty or len(frame) < 2:
        return {}, [], []

    working = frame.reset_index(drop=True)
    signals = buy_and_hold_signal(working)
    # Next-bar execution, identical to the strategy path.
    execution_signal = signals.shift(1).fillna(0)

    portfolio, _markers = simulate(
        working,
        execution_signal,
        initial_capital,
        transaction_fee,
        slippage,
    )
    if not portfolio.equity_curve:
        return {}, [], []

    metrics = compute_metrics(
        portfolio.equity_curve, portfolio.realized_trades, initial_capital
    )
    equity_curve = [
        {
            "timestamp": str(point["timestamp"]),
            "equity": float(point["equity"]),
            "price": float(point["price"]),
        }
        for point in portfolio.equity_curve
    ]
    drawdown = [
        {"timestamp": str(point["timestamp"]), "drawdown": float(point["drawdown"])}
        for point in drawdown_series(portfolio.equity_curve)
    ]
    return metrics, equity_curve, drawdown
