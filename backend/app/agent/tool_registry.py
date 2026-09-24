"""OpenAI-style tool registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent.tools.stock_tools import (
    BacktestInput,
    CompareInput,
    ForecastInput,
    IndicatorInput,
    MarketSummaryInput,
    StockQueryInput,
    calculate_indicators,
    compare_models,
    forecast_stock,
    get_market_summary,
    query_stock_data,
    run_backtest,
)

TOOL_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "query_stock_data": query_stock_data,
    "calculate_indicators": calculate_indicators,
    "forecast_stock": forecast_stock,
    "compare_models": compare_models,
    "run_backtest": run_backtest,
    "get_market_summary": get_market_summary,
}

TOOL_MODELS = {
    "query_stock_data": StockQueryInput,
    "calculate_indicators": IndicatorInput,
    "forecast_stock": ForecastInput,
    "compare_models": CompareInput,
    "run_backtest": BacktestInput,
    "get_market_summary": MarketSummaryInput,
}


def openai_tools() -> list[dict[str, Any]]:
    """Return JSON schemas for OpenAI function calling."""
    specs = []
    descriptions = {
        "query_stock_data": "Lấy dữ liệu OHLCV thật từ lakehouse, không được bịa giá.",
        "calculate_indicators": "Tính SMA, EMA, RSI, MACD, Bollinger từ dữ liệu thật.",
        "forecast_stock": "Chạy dự báo bằng mô hình đã train. Báo lỗi nếu chưa train.",
        "compare_models": "So sánh MAE/RMSE/MAPE/Directional Accuracy của các mô hình đã train.",
        "run_backtest": "Chạy backtest lịch sử MA Crossover hoặc RSI. Không phải giao dịch thật.",
        "get_market_summary": "Tóm tắt giá, biến động và RSI hiện tại từ dữ liệu lakehouse.",
    }
    for name, model in TOOL_MODELS.items():
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": descriptions[name],
                    "parameters": model.model_json_schema(),
                },
            }
        )
    return specs


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOL_FUNCTIONS:
        return {"error": f"Unknown tool: {name}"}
    model = TOOL_MODELS[name]
    payload = model.model_validate(arguments)
    return TOOL_FUNCTIONS[name](**payload.model_dump())
