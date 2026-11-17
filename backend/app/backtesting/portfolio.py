"""Simple long-only portfolio used by the research backtester."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.backtesting.trade import Trade

# The relative tolerance used when checking whether an order fits inside the
# available cash. See `Portfolio.buy` for why it is needed.
_CASH_TOLERANCE = 1e-9


@dataclass
class Portfolio:
    """Cash plus a single-asset position."""

    initial_capital: float
    cash: float
    position_qty: float = 0.0
    avg_entry_price: float = 0.0
    entry_time: object | None = None
    # The fee charged when the position was opened. Remembered so the
    # closed trade's PnL can include it - see `sell`.
    entry_fees: float = 0.0
    realized_trades: list[Trade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    @property
    def is_long(self) -> bool:
        return self.position_qty > 0

    def mark_to_market(self, timestamp, price: float) -> float:
        equity = self.cash + self.position_qty * price
        self.equity_curve.append({"timestamp": timestamp, "equity": equity, "price": price})
        return equity

    def buy(self, timestamp, price: float, fee_pct: float, slippage_pct: float) -> None:
        if self.is_long or self.cash <= 0:
            return
        fill_price = price * (1 + slippage_pct)
        spendable = self.cash / (1 + fee_pct)
        quantity = spendable / fill_price
        fees = quantity * fill_price * fee_pct
        cost = quantity * fill_price + fees
        # WHY THE TOLERANCE: in exact arithmetic `cost` is identical to
        # `spendable`, which is at most `cash`. But floating point makes
        # `cost` land a hair ABOVE `cash` - on AAPL it was
        # 10910.740000000002 against 10910.74, a gap of 1.8e-12.
        #
        # The bare `cost > self.cash` check therefore REJECTED the order,
        # and because the portfolio never held a position again, every
        # later buy was skipped too. The visible symptom was a backtest
        # that reported a single trade for a strategy that fires eleven
        # times over the same history - the strategy looked broken when
        # in fact it was never allowed to trade.
        #
        # The tolerance is relative to the cash so it scales with the size
        # of the account, and it is far below the smallest amount of money
        # that could ever matter.
        if cost > self.cash * (1 + _CASH_TOLERANCE) or quantity <= 0:
            return
        self.cash = max(self.cash - cost, 0.0)
        self.position_qty = quantity
        self.avg_entry_price = fill_price
        self.entry_time = timestamp
        # The entry fee is remembered so the CLOSED trade's PnL can
        # include it.
        #
        # WHY: the cash is reduced by the entry fee right here, so the
        # equity curve already reflects it. But the trade's PnL used to be
        # computed as `exit proceeds - exit fees - entry notional`, which
        # left the entry fee out of the PnL. The consequences were real:
        #
        #   * sum(trade.pnl) did NOT equal final_capital - initial_capital
        #     (on AAPL over 10 years the gap was 120.32, exactly the
        #     entry fees),
        #   * a trade that lost money could still be reported as a WIN,
        #     because the fee that pushed it underwater was not counted,
        #   * so the win rate and the profit factor were both wrong.
        #
        # Storing the entry fee makes the trade's PnL the true net result
        # of the round trip, so the two numbers agree.
        self.entry_fees = float(fees)

    def sell(self, timestamp, price: float, fee_pct: float, slippage_pct: float) -> Trade | None:
        if not self.is_long:
            return None
        fill_price = price * (1 - slippage_pct)
        proceeds = self.position_qty * fill_price
        fees = proceeds * fee_pct
        net = proceeds - fees
        # The PnL is the NET result of the round trip: the exit proceeds,
        # minus BOTH fees, minus the capital that was committed at entry.
        entry_notional = self.position_qty * self.avg_entry_price
        pnl = net - self.entry_fees - entry_notional
        cost_basis = entry_notional + self.entry_fees
        return_pct = pnl / cost_basis if cost_basis else 0.0
        trade = Trade(
            entry_time=self.entry_time,
            exit_time=timestamp,
            entry_price=float(self.avg_entry_price),
            exit_price=float(fill_price),
            quantity=float(self.position_qty),
            side="long",
            pnl=float(pnl),
            return_pct=float(return_pct),
            # Both fees belong to the trade, not just the exit one.
            fees=float(self.entry_fees + fees),
        )
        self.cash += net
        self.position_qty = 0.0
        self.avg_entry_price = 0.0
        self.entry_time = None
        self.entry_fees = 0.0
        self.realized_trades.append(trade)
        return trade
