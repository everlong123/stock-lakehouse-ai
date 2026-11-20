"""Prevent cross-instrument answers and historical estimates posing as forecasts."""

import pytest

from app.agent import agent
from app.agent.tools import stock_tools
from app.core.constants import ALL_SYMBOLS


@pytest.fixture(autouse=True)
def isolated_agent_catalog(monkeypatch):
    monkeypatch.setattr(agent, "stored_symbols", lambda: frozenset())


@pytest.mark.parametrize("symbol", sorted(set(ALL_SYMBOLS)))
def test_every_configured_ticker_survives_question_extraction(symbol):
    assert agent._extract_symbol(f"Giá {symbol} hôm nay", "AAPL") == symbol
    assert agent._extract_symbol(f"Giá {symbol.lower()} hôm nay", "AAPL") == symbol
    assert agent._extract_symbol(f"Backtest MA Crossover {symbol}", "AAPL") == symbol


@pytest.mark.parametrize("text,symbol", [("BRK.B", "B"), ("BTC-USD", "BTC"), ("^GSPC", "GSPC")])
def test_ticker_fragments_do_not_name_another_instrument(text, symbol):
    assert not agent._mentions_symbol(text, symbol)


def test_forecast_tool_never_returns_history_when_future_is_blocked(monkeypatch):
    monkeypatch.setattr(stock_tools.ForecastingService, "predict", lambda *args: {
        "forecast_available": False,
        "forecast_reason": "Input data is 1 trading session behind.",
        "predictions": [{"timestamp": "2026-11-18", "actual": 100., "predicted": 101.}],
    })
    result = stock_tools.forecast_stock("FPT")
    assert result["latest_predicted"] is None
    assert result["target_timestamp"] is None
    assert result["forecast_available"] is False
    answer = agent._render_local_answer("Dự báo FPT", {"forecast_stock": result})
    assert result["forecast_reason"] in answer
    assert "101.0000" not in answer


def test_forecast_tool_identifies_future_target_even_if_history_is_last(monkeypatch):
    monkeypatch.setattr(stock_tools.ForecastingService, "predict", lambda *args: {
        "forecast_available": True,
        "predictions": [
            {"timestamp": "2026-11-20", "actual": None, "predicted": 102.},
            {"timestamp": "2026-11-18", "actual": 100., "predicted": 101.},
        ],
    })
    result = stock_tools.forecast_stock("AAPL", horizon=1)
    assert result["latest_predicted"] == 102.
    assert result["target_timestamp"] == "2026-11-20"
    assert result["forecast_available"] is True


def test_offline_walk_forward_runs_the_requested_validator(monkeypatch):
    calls = []

    def execute(name, arguments):
        calls.append((name, arguments))
        return {"symbol": arguments["symbol"], "strategy": arguments["strategy"], "summary": {"total_windows": 3}}

    monkeypatch.setattr(agent, "execute_tool", execute)
    result = agent.StockAnalysisAgent()._local_reply("Walk-forward RSI ^GSPC", "AAPL")
    assert calls == [("run_walk_forward", {"symbol": "^GSPC", "strategy": "rsi_strategy"})]
    assert "3 cửa sổ" in result["assistant_message"]


def test_llm_empty_answer_does_not_turn_failed_backtest_into_zero_returns(monkeypatch):
    error = "Need at least 60 bars to backtest this strategy."
    responses = iter([
        {"tool_calls": [{"id": "bt", "name": "run_backtest", "arguments": '{"symbol":"AVB"}'}]},
        {"content": ""},
    ])
    instance = agent.StockAnalysisAgent()
    monkeypatch.setattr(instance.llm, "chat", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(agent, "execute_tool", lambda *args: {"error": error})
    result = instance._llm_reply("Backtest AVB", "AAPL")
    assert result["tools"][0]["error"] == error
    assert error in result["assistant_message"]
    assert "Total Return=" not in result["assistant_message"]


def test_default_refresh_includes_every_configured_instrument(monkeypatch):
    from app.services.auto_refresh import AutoRefreshService

    monkeypatch.delenv("AUTO_REFRESH_SYMBOLS", raising=False)
    symbols = AutoRefreshService()._symbols
    assert set(symbols) == set(ALL_SYMBOLS)
    assert len(symbols) == len(set(symbols))


def test_agent_universe_count_is_unique_configuration_not_data_coverage():
    from app.agent.tools.system_tools import get_symbols_info
    from app.agent.tool_registry import openai_tools

    info = get_symbols_info()
    assert info["total_symbols"] == len(set(ALL_SYMBOLS))
    assert "configured" in info["symbol_count_scope"]
    summary = next(t["function"] for t in openai_tools() if t["function"]["name"] == "get_market_summary")
    assert "symbol" in summary["parameters"]["properties"]


def test_stored_ticker_outside_curated_list_is_not_replaced_by_default(monkeypatch):
    monkeypatch.setattr(agent, "stored_symbols", lambda: frozenset({"WBA", "BK"}))
    assert agent._extract_symbol("Giá wba hôm nay", "AAPL") == "WBA"
    assert agent._extract_symbol("Price WBA on the market", "AAPL") == "WBA"
    assert agent._extract_symbol("Giá WBA so với hôm qua", "AAPL") == "WBA"
    assert agent._extract_symbol("Backtest MA Crossover BK", "AAPL") == "BK"
    assert agent._extract_symbol("RSI", "WBA") == "WBA"
    assert agent._is_valid_ticker("wba")
    assert not agent._is_valid_ticker("MADEUP")


def test_llm_summary_without_symbol_uses_requested_archived_ticker(monkeypatch):
    monkeypatch.setattr(agent, "stored_symbols", lambda: frozenset({"WBA"}))
    calls = []
    responses = iter([
        {"tool_calls": [
            {"id": "summary", "name": "get_market_summary", "arguments": "{}"},
            {"id": "system", "name": "get_symbols_info", "arguments": "{}"},
        ]},
        {"content": "WBA"},
    ])
    instance = agent.StockAnalysisAgent()
    monkeypatch.setattr(instance.llm, "chat", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(agent, "execute_tool", lambda name, args: calls.append((name, args.copy())) or {})
    instance._llm_reply("Price WBA on the market", "AAPL")
    assert calls == [("get_market_summary", {"symbol": "WBA"}), ("get_symbols_info", {})]


def test_llm_cannot_reject_stored_ticker_without_verifying_tools(monkeypatch):
    monkeypatch.setattr(agent, "stored_symbols", lambda: frozenset({"BK"}))
    instance = agent.StockAnalysisAgent()
    monkeypatch.setattr(instance.llm, "chat", lambda *args, **kwargs: {"content": "BK is unavailable"})
    calls = []
    monkeypatch.setattr(agent, "execute_tool", lambda name, args: calls.append((name, args.copy())) or {
        "symbol": args["symbol"], "close": 42., "change_pct": 0., "volume": 100.,
    })
    result = instance._llm_reply("Giá BK hôm nay", "AAPL")
    assert calls and all(args["symbol"] == "BK" for _, args in calls)
    assert "42" in result["assistant_message"]
    assert "BK is unavailable" not in result["assistant_message"]


def test_catalog_lists_only_local_instruments_with_data_and_caches(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app.services import symbol_catalog

    bronze = tmp_path / "bronze"
    (bronze / "symbol=WBA").mkdir(parents=True)
    (bronze / "symbol=WBA" / "rows.parquet").touch()
    (bronze / "symbol=EMPTY").mkdir()
    calls = []

    def storage():
        calls.append(True)
        return SimpleNamespace(backend_name="local", root=tmp_path)

    monkeypatch.setattr(symbol_catalog, "get_storage_backend", storage)
    monkeypatch.setattr(symbol_catalog, "_symbols", frozenset())
    monkeypatch.setattr(symbol_catalog, "_expires_at", 0.)
    assert symbol_catalog.stored_symbols() == frozenset({"WBA"})
    assert symbol_catalog.stored_symbols() == frozenset({"WBA"})
    assert len(calls) == 1


def test_catalog_retains_cached_inventory_during_storage_failure(monkeypatch):
    from app.services import symbol_catalog

    def unavailable():
        raise OSError("storage unavailable")

    monkeypatch.setattr(symbol_catalog, "get_storage_backend", unavailable)
    monkeypatch.setattr(symbol_catalog, "_symbols", frozenset({"WBA"}))
    monkeypatch.setattr(symbol_catalog, "_expires_at", 0.)
    assert symbol_catalog.stored_symbols() == frozenset({"WBA"})


def test_catalog_discovers_minio_prefixes_without_reading_history(monkeypatch):
    from types import SimpleNamespace
    from app.services import symbol_catalog

    seen = []

    def objects(bucket, **kwargs):
        seen.append((bucket, kwargs))
        return [SimpleNamespace(object_name="symbol=WBA/"), SimpleNamespace(object_name="symbol=BK/"), SimpleNamespace(object_name="other/")]

    storage = SimpleNamespace(
        backend_name="minio", _bucket=lambda layer: "stock-" + layer,
        client=SimpleNamespace(list_objects=objects),
    )
    monkeypatch.setattr(symbol_catalog, "get_storage_backend", lambda: storage)
    monkeypatch.setattr(symbol_catalog, "_symbols", frozenset())
    monkeypatch.setattr(symbol_catalog, "_expires_at", 0.)
    assert symbol_catalog.stored_symbols() == frozenset({"WBA", "BK"})
    assert seen == [("stock-bronze", {"prefix": "symbol=", "recursive": False})]


@pytest.mark.parametrize("symbol,expected", [("FRT", "USD"), ("NET", "USD"), ("DBC", "USD"), ("HDB", "VND"), ("FRT.VN", "VND")])
def test_colliding_tickers_keep_the_currency_of_the_stored_instrument(symbol, expected):
    from app.core.constants import currency_for_symbol

    assert currency_for_symbol(symbol) == expected
