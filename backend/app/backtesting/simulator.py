"""Shared bar-by-bar trade simulation used by the backtest engine and walk-forward.

WHY this module exists
----------------------
Both :class:`~app.backtesting.engine.BacktestEngine` and
:class:`~app.backtesting.walk_forward.WalkForwardValidator` need to replay a
price series against a strategy's signals. They used to each carry their own
copy of that loop, and both copies indexed the DataFrame row-by-row with
``frame.iloc[index]``.

``DataFrame.iloc[i]`` constructs a brand-new pandas Series for every single
bar. On a 10-year daily history that is ~2500 Series allocations per pass,
which is roughly 50x slower than iterating over pre-extracted Python values.
The walk-forward validator runs the loop twice per window (train + test) over
~175 windows, so the whole request was dominated by Series construction
rather than by the actual strategy maths. Under the load of a concurrent
auto-refresh pass that turned a 2s response into a 150s one, which is what
pushed the UI past its 90s timeout.

This module does the extraction once and hands both callers the same fast
implementation, so the two paths cannot drift apart.
"""

from __future__ import annotations

import pandas as pd

from app.backtesting.portfolio import Portfolio


def _extract(frame: pd.DataFrame) -> tuple[list, list, list]:
    """Return (timestamps, opens, closes) as plain Python lists.

    The lists hold the raw values, so a missing open stays ``None``/``NaN``
    and is resolved to the close by the caller - exactly like the original
    ``float(row["open"]) if pd.notna(row["open"]) else float(row["close"])``.
    """
    return (
        frame["timestamp"].tolist(),
        frame["open"].tolist(),
        frame["close"].tolist(),
    )


def simulate(
    frame: pd.DataFrame,
    execution_signal: pd.Series,
    initial_capital: float,
    transaction_fee: float,
    slippage: float,
) -> tuple[Portfolio, list[dict]]:
    """Replay ``frame`` against ``execution_signal`` and return the portfolio.

    Args:
        frame: OHLCV rows, already sorted by timestamp.
        execution_signal: Signal series aligned to ``frame``; a positive value
            buys on that bar's open, a negative value sells.
        initial_capital: Starting cash.
        transaction_fee: Fee as a fraction of the traded notional.
        slippage: Slippage as a fraction of the fill price.

    Returns:
        ``(portfolio, markers)`` where ``markers`` records the bars on which
        a position was opened or closed, for chart annotation.
    """
    portfolio = Portfolio(initial_capital=initial_capital, cash=initial_capital)
    markers: list[dict] = []

    timestamps, opens, closes = _extract(frame)
    signal_values = execution_signal.tolist()

    for index in range(len(frame)):
        exec_price = opens[index]
        if exec_price is None or pd.isna(exec_price):
            exec_price = closes[index]
        exec_price = float(exec_price)

        signal = signal_values[index]
        timestamp = timestamps[index]

        if signal > 0:
            before = portfolio.is_long
            portfolio.buy(timestamp, exec_price, transaction_fee, slippage)
            if portfolio.is_long and not before:
                markers.append({"timestamp": str(timestamp), "price": exec_price, "side": "buy"})
        elif signal < 0:
            trade = portfolio.sell(timestamp, exec_price, transaction_fee, slippage)
            if trade is not None:
                markers.append({"timestamp": str(timestamp), "price": exec_price, "side": "sell"})

        portfolio.mark_to_market(timestamp, float(closes[index]))

    # Close any position still open at the end of the series, so the final
    # equity reflects a flat book rather than an open mark.
    if portfolio.is_long:
        portfolio.sell(timestamps[-1], float(closes[-1]), transaction_fee, slippage)
        # The forced close changed the book, so the LAST equity point -
        # which was marked while the position was still open, and therefore
        # still included the exit fee and the slippage - has to be replaced
        # with the value of the now-flat book.
        #
        # WHY: without this the last equity point was higher than the real
        # final capital by exactly the cost of closing the position. The
        # backtester then reported a final capital that no trade could
        # reconcile with: on the test fixture the two disagreed by 12.63,
        # which is the closing cost of the last position.
        if portfolio.equity_curve:
            portfolio.equity_curve[-1]["equity"] = portfolio.cash

    return portfolio, markers
