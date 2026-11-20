"""Chart ranges preserve all stored sessions, including histories beyond old caps."""

import pandas as pd
import pytest

from app.api.v1.endpoints.stocks import get_stock
from app.services import dashboard_service
from app.services.dashboard_service import DashboardService
from app.services.market_service import MarketService
from conftest import make_ohlcv


@pytest.mark.parametrize("endpoint", ["dashboard", "stocks"])
@pytest.mark.parametrize("window_days", [None, 92])
def test_chart_history_keeps_the_entire_requested_window(monkeypatch, endpoint, window_days):
    history = make_ohlcv(rows=5101)
    start = None if window_days is None else history.iloc[-1].timestamp - pd.Timedelta(days=window_days)
    expected = history if start is None else history[history.timestamp >= start]
    market = MarketService.__new__(MarketService)

    def load_history(symbol, start=None, end=None, interval="1d"):
        assert symbol == "AAPL"
        assert interval == "1d"
        assert end is None
        return history if start is None else history[history.timestamp >= start]

    monkeypatch.setattr(market, "get_history", load_history)
    if endpoint == "stocks":
        result = get_stock("aapl", start=start, interval="1d", service=market)["data"]
        rows = result["rows"]
        assert result["count"] == len(rows)
    else:
        dashboard = DashboardService.__new__(DashboardService)
        dashboard.market = market
        monkeypatch.setattr(dashboard_service, "list_trained_models", lambda _symbol: [])
        monkeypatch.setattr(dashboard, "_layer_counts", lambda _symbol: {})
        rows = dashboard.build("AAPL", start=start)["candles"]

    assert len(rows) == len(expected)
    assert rows[0]["timestamp"] == str(expected.iloc[0].timestamp)
    assert rows[-1]["timestamp"] == str(expected.iloc[-1].timestamp)
