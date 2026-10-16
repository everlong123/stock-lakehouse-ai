"""Function-calling tool registry shared by every LLM provider.

The schemas are written in the OpenAI function-calling JSON shape because that
format is the lingua franca: Gemini's converter in
:mod:`app.agent.llm_client` translates them into the equivalent Gemini
``function_declarations`` payload, so a single schema definition works for
both the live Gemini client and the keyword router fallback.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent.tools.fundamental_tools import (
    BalanceSheetInput,
    CashFlowInput,
    FundamentalMetricsInput,
    get_balance_sheet,
    get_cash_flow,
    get_fundamental_metrics,
    get_income_statement,
    get_market_index,
    get_orderbook,
    IncomeStatementInput,
    MarketIndexInput,
    OrderBookInput,
)
from app.agent.tools.news_tools import (
    get_market_news,
    get_news_for_symbol,
    get_sentiment_summary,
    get_sentiment_timeseries,
    MarketNewsInput,
    NewsInput,
    SentimentSummaryInput,
    SentimentTimeseriesInput,
)
from app.agent.tools.stock_tools import (
    BacktestInput,
    calculate_indicators,
    CompareInput,
    compare_models,
    forecast_stock,
    ForecastInput,
    IndicatorInput,
    run_backtest,
    StockQueryInput,
    get_market_summary,
    query_stock_data,
)
from app.agent.tools.system_tools import (
    get_storage_stats,
    get_symbols_info,
    get_system_architecture,
    get_trained_models,
    StorageStatsInput,
    SymbolsInfoInput,
    SystemArchitectureInput,
    TrainedModelsInput,
)
from app.agent.tools.walkforward_tools import WalkForwardInput, run_walk_forward

TOOL_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    # Stock data
    "query_stock_data": query_stock_data,
    "get_market_summary": get_market_summary,
    # Technical indicators
    "calculate_indicators": calculate_indicators,
    # Forecasting
    "forecast_stock": forecast_stock,
    "compare_models": compare_models,
    # Backtesting
    "run_backtest": run_backtest,
    "run_walk_forward": run_walk_forward,
    # News & Sentiment
    "get_news_for_symbol": get_news_for_symbol,
    "get_sentiment_summary": get_sentiment_summary,
    "get_sentiment_timeseries": get_sentiment_timeseries,
    "get_market_news": get_market_news,
    # Fundamental
    "get_fundamental_metrics": get_fundamental_metrics,
    "get_income_statement": get_income_statement,
    "get_balance_sheet": get_balance_sheet,
    "get_cash_flow": get_cash_flow,
    # Market data
    "get_market_index": get_market_index,
    "get_orderbook": get_orderbook,
    # System / project metadata (NEW)
    "get_symbols_info": get_symbols_info,
    "get_trained_models": get_trained_models,
    "get_system_architecture": get_system_architecture,
    "get_storage_stats": get_storage_stats,
}

TOOL_MODELS = {
    "query_stock_data": StockQueryInput,
    "get_market_summary": None,
    "calculate_indicators": IndicatorInput,
    "forecast_stock": ForecastInput,
    "compare_models": CompareInput,
    "run_backtest": BacktestInput,
    "run_walk_forward": WalkForwardInput,
    "get_news_for_symbol": NewsInput,
    "get_sentiment_summary": SentimentSummaryInput,
    "get_sentiment_timeseries": SentimentTimeseriesInput,
    "get_market_news": MarketNewsInput,
    "get_fundamental_metrics": FundamentalMetricsInput,
    "get_income_statement": IncomeStatementInput,
    "get_balance_sheet": BalanceSheetInput,
    "get_cash_flow": CashFlowInput,
    "get_market_index": MarketIndexInput,
    "get_orderbook": OrderBookInput,
    # System tools (NEW)
    "get_symbols_info": SymbolsInfoInput,
    "get_trained_models": TrainedModelsInput,
    "get_system_architecture": SystemArchitectureInput,
    "get_storage_stats": StorageStatsInput,
}

TOOL_DESCRIPTIONS = {
    "query_stock_data": "Lấy dữ liệu OHLCV thật từ lakehouse, không được bịa giá.",
    "get_market_summary": "Tóm tắt giá, biến động và RSI hiện tại từ dữ liệu lakehouse.",
    "calculate_indicators": "Tính SMA, EMA, RSI, MACD, Bollinger từ dữ liệu thật.",
    "forecast_stock": "Chạy dự báo bằng mô hình đã train. Báo lỗi nếu chưa train.",
    "compare_models": "So sánh MAE/RMSE/MAPE/Directional Accuracy của các mô hình đã train.",
    "run_backtest": "Chạy backtest lịch sử MA Crossover hoặc RSI. Không phải giao dịch thật.",
    "run_walk_forward": "Chạy walk-forward validation - phương pháp backtest nghiêm ngặt, đánh giá trên nhiều windows để tránh overfitting.",
    "get_news_for_symbol": "Lấy tin tức có phân tích sentiment cho một mã chứng khoán.",
    "get_sentiment_summary": "Tóm tắt sentiment (tích cực/tiêu cực) cho một mã trong N ngày.",
    "get_sentiment_timeseries": "Lấy dữ liệu sentiment theo thời gian để vẽ biểu đồ xu hướng.",
    "get_market_news": "Lấy tin tức thị trường chung (không phải tin riêng của một mã).",
    "get_fundamental_metrics": "Lấy metrics tài chính (P/E, P/B, ROE, ROA, v.v.) cho một mã.",
    "get_income_statement": "Lấy báo cáo thu nhập (doanh thu, lợi nhuận) qua các năm.",
    "get_balance_sheet": "Lấy bảng cân đối kế toán (tài sản, nợ, vốn chủ sở hữu).",
    "get_cash_flow": "Lấy báo cáo lưu chuyển tiền tệ (dòng tiền hoạt động, đầu tư, tài chính).",
    "get_market_index": "Lấy dữ liệu chỉ số thị trường US (^GSPC: S&P 500, ^DJI: Dow Jones, ^IXIC: NASDAQ).",
    "get_orderbook": "Lấy sổ lệnh (bid/ask) hiện tại cho một mã.",
    # System / project metadata tools (NEW)
    "get_symbols_info": "Trả về thống kê số mã hệ thống hỗ trợ (US, global, VN, crypto, indexes) kèm danh sách data providers. Dùng khi user hỏi 'có bao nhiêu mã?', 'track những mã nào?', 'có mã Việt Nam không?'.",
    "get_trained_models": "Liệt kê các mô hình ML đã train trong hệ thống (linear_regression, arima, lstm, xgboost) kèm MAE/RMSE/MAPE/DA. Lọc theo symbol nếu cần. Dùng khi user hỏi 'đã train model nào?', 'model nào đã train cho VCB?'.",
    "get_system_architecture": "Mô tả kiến trúc runtime của hệ thống: Bronze/Silver/Gold, providers, tech stack (FastAPI/MinIO/MySQL/Kafka/Iceberg), auto-refresh, danh sách 16 tool. Dùng khi user hỏi 'kiến trúc?', 'stack gì?', 'hệ thống gồm gì?'.",
    "get_storage_stats": "Thống kê số object + dung lượng từng bucket MinIO (bronze/silver/gold/models/news/fundamentals) + số symbol có dữ liệu thật ở mỗi layer. Dùng khi user hỏi 'MinIO có bao nhiêu file?', 'Bronze có dữ liệu chưa?'.",
}


def openai_tools() -> list[dict[str, Any]]:
    """Return JSON schemas for OpenAI function calling."""
    specs = []
    for name, description in TOOL_DESCRIPTIONS.items():
        model = TOOL_MODELS.get(name)
        schema = {"type": "object", "properties": {}, "required": []}
        if model is not None:
            schema = model.model_json_schema()

        specs.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema,
            },
        })
    return specs


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOL_FUNCTIONS:
        return {"error": f"Unknown tool: {name}"}
    try:
        model = TOOL_MODELS.get(name)
        if model is not None:
            payload = model.model_validate(arguments)
            kwargs = payload.model_dump()
        else:
            kwargs = arguments
        return TOOL_FUNCTIONS[name](**kwargs)
    except Exception as exc:
        return {"error": str(exc)}
