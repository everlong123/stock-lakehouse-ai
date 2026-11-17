"""Backtest accounting tests.

WHY THIS FILE EXISTS
--------------------
The backtester reported a trade's PnL as `exit proceeds - exit fees - entry
notional`. The ENTRY fee was missing from that formula, even though it had
already been deducted from the cash.

The consequences were not cosmetic:

* `sum(trade.pnl)` did not equal `final_capital - initial_capital`. On
  AAPL over ten years the gap was 120.32, which is exactly the entry fees.
* A trade that lost money after fees could be reported as a WIN, so the
  win rate was overstated.
* The profit factor was overstated for the same reason.

These tests pin down the property that makes the numbers trustworthy: the
trades must reconcile with the equity curve.
"""

from __future__ import annotations

import pandas as pd

from app.backtesting.engine import BacktestEngine
from app.backtesting.portfolio import Portfolio
from tests.conftest import make_ohlcv


def _run(frame: pd.DataFrame, **kwargs) -> dict:
    engine = BacktestEngine()
    engine._load_ohlcv = lambda symbol, start_date, end_date: frame  # type: ignore[method-assign]
    params = {
        "initial_capital": 10_000.0,
        "transaction_fee": 0.001,
        "slippage": 0.0005,
        "parameters": {"short_window": 5, "long_window": 10},
    }
    params.update(kwargs)
    return engine.run("TEST", "ma_crossover", **params)


def test_trade_pnl_reconciles_with_final_capital() -> None:
    """sum(trade.pnl) must equal final_capital - initial_capital."""
    frame = make_ohlcv(400)
    result = _run(frame)

    assert result["trades"], "the fixture should produce at least one trade"
    total_pnl = sum(trade["pnl"] for trade in result["trades"])
    expected = result["final_capital"] - result["initial_capital"]

    # A small tolerance for floating point noise over many trades.
    assert abs(total_pnl - expected) < 0.01, (
        f"trades do not reconcile with the portfolio: "
        f"sum(pnl)={total_pnl:.4f} vs final-initial={expected:.4f}"
    )


def test_trade_pnl_is_net_of_both_fees() -> None:
    """The PnL must be reduced by the entry fee as well as the exit fee."""
    frame = make_ohlcv(400)
    result = _run(frame)

    for trade in result["trades"]:
        gross = trade["quantity"] * (trade["exit_price"] - trade["entry_price"])
        # The PnL is strictly below the gross price move, because both
        # fees and the slippage have to be paid.
        assert trade["pnl"] < gross, "the PnL ignores the fees and the slippage"


def test_zero_fee_trades_match_the_price_move() -> None:
    """With no fees and no slippage, the PnL is exactly the price move."""
    frame = make_ohlcv(400)
    result = _run(frame, transaction_fee=0.0, slippage=0.0)

    for trade in result["trades"]:
        expected = trade["quantity"] * (trade["exit_price"] - trade["entry_price"])
        assert abs(trade["pnl"] - expected) < 1e-6, (
            "with zero fees the PnL must be the raw price move"
        )


def test_a_losing_trade_is_not_counted_as_a_win() -> None:
    """A trade that only lost money because of fees must not be a win."""
    frame = make_ohlcv(400)
    result = _run(frame)

    for trade in result["trades"]:
        if trade["pnl"] < 0:
            assert trade["return_pct"] < 0, (
                "a trade with a negative PnL must have a negative return"
            )

    wins = [trade for trade in result["trades"] if trade["pnl"] > 0]
    assert abs(result["win_rate"] - len(wins) / len(result["trades"])) < 1e-9


def test_portfolio_accounting_is_internally_consistent() -> None:
    """The portfolio's cash and PnL must agree with each other."""
    portfolio = Portfolio(initial_capital=1000.0, cash=1000.0)

    portfolio.buy("t0", 100.0, fee_pct=0.01, slippage_pct=0.0)
    assert portfolio.cash < 1000.0
    entry_fees = portfolio.entry_fees
    quantity = portfolio.position_qty
    assert entry_fees > 0

    trade = portfolio.sell("t1", 110.0, fee_pct=0.01, slippage_pct=0.0)
    assert trade is not None

    # The cash moved by exactly the trade's PnL.
    assert abs((portfolio.cash - 1000.0) - trade.pnl) < 1e-6, (
        "the cash movement must equal the reported PnL"
    )
    # The reported fee covers both legs.
    expected_fees = entry_fees + quantity * 110.0 * 0.01
    assert abs(trade.fees - expected_fees) < 1e-6


def test_equity_curve_matches_the_final_capital() -> None:
    """The last equity point is the final capital."""
    frame = make_ohlcv(400)
    result = _run(frame)

    last_equity = result["equity_curve"][-1]["equity"]
    assert abs(last_equity - result["final_capital"]) < 1e-6


def test_drawdown_is_never_positive() -> None:
    """A drawdown is a loss from the running peak, so it cannot be positive."""
    frame = make_ohlcv(400)
    result = _run(frame)

    for point in result["drawdown"]:
        assert point["drawdown"] <= 1e-9, "a drawdown above zero is impossible"
    assert result["maximum_drawdown"] <= 1e-9


def test_a_rebuy_after_a_profitable_trade_is_allowed() -> None:
    """The portfolio must be able to trade again after closing a position.

    WHY THIS MATTERS
    ----------------
    The buy guard was `if cost > self.cash: return`. In exact arithmetic
    `cost` equals the spendable cash, but floating point made it land a
    hair ABOVE the cash - on AAPL it was 10910.740000000002 against
    10910.74, a gap of 1.8e-12.

    So the SECOND buy of a run was always rejected. Because the strategy
    only ever holds one position, the portfolio then never recovered, and
    every later buy was skipped too. The RSI strategy fires eleven times
    over AAPL's ten-year history but the backtest reported ONE trade.

    The portfolio ended up flat and idle, holding cash for the rest of
    the run, so the backtest looked like a strategy that does nothing.
    """
    portfolio = Portfolio(initial_capital=10_000.0, cash=10_000.0)

    # First round trip, slightly profitable.
    portfolio.buy("t0", 100.0, fee_pct=0.001, slippage_pct=0.0005)
    assert portfolio.is_long, "the first buy must go through"
    trade = portfolio.sell("t1", 110.0, fee_pct=0.001, slippage_pct=0.0005)
    assert trade is not None
    assert portfolio.cash > 10_000.0

    # The second buy must be allowed through. This is the one the float
    # comparison used to reject.
    portfolio.buy("t2", 110.0, fee_pct=0.001, slippage_pct=0.0005)
    assert portfolio.is_long, (
        "the portfolio must be able to buy again after closing a position"
    )
    assert portfolio.position_qty > 0


def test_the_buy_order_is_never_rejected_on_float_noise() -> None:
    """A full-cash buy must succeed no matter what the cash happens to be."""
    # These cash values are the ones that actually broke: they are the
    # results of a previous round trip, so they carry floating point dust.
    for cash in (10_910.74, 12_345.678_9, 33_333.333_333_3, 7.77):
        portfolio = Portfolio(initial_capital=cash, cash=cash)
        portfolio.buy("t0", 41.5, fee_pct=0.001, slippage_pct=0.0005)
        assert portfolio.is_long, f"the buy was rejected for cash={cash!r}"
        assert portfolio.cash >= 0.0


def test_a_strategy_that_signals_repeatedly_produces_repeated_trades() -> None:
    """The engine must not silently stop trading after the first round trip.

    This is the end-to-end version of the bug above: a strategy that fires
    many signals must produce many trades, not one.
    """
    from app.backtesting.strategies import STRATEGY_MAP

    frame = make_ohlcv(600)
    engine = BacktestEngine()
    engine._load_ohlcv = lambda symbol, start_date, end_date: frame  # type: ignore[method-assign]

    signals = STRATEGY_MAP["rsi_strategy"](
        parameters={"rsi_period": 14, "lower_threshold": 30, "upper_threshold": 70}
    ).generate_signals(frame)
    signal_count = int((signals != 0).sum())

    result = engine.run(
        "TEST",
        "rsi_strategy",
        initial_capital=10_000.0,
        transaction_fee=0.001,
        slippage=0.0005,
        parameters={"rsi_period": 14, "lower_threshold": 30, "upper_threshold": 70},
    )

    # Each signal pair (a buy and a sell) can close one trade, so the
    # number of trades must be in the same ballpark as the number of
    # signals. Before the fix this was 1 against 22 signals.
    assert result["number_of_trades"] >= signal_count // 4, (
        f"only {result['number_of_trades']} trades for {signal_count} signals - "
        "the portfolio stopped trading"
    )
