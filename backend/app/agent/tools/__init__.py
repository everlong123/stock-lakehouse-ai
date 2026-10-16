"""Tool package."""

from app.agent.tools.stock_tools import (
    calculate_indicators,
    compare_models,
    forecast_stock,
    get_market_summary,
    query_stock_data,
    run_backtest,
)
from app.agent.tools.system_tools import (
    get_storage_stats,
    get_symbols_info,
    get_system_architecture,
    get_trained_models,
)

__all__ = [
    "query_stock_data",
    "calculate_indicators",
    "forecast_stock",
    "compare_models",
    "run_backtest",
    "get_market_summary",
    # System / project metadata (NEW)
    "get_symbols_info",
    "get_trained_models",
    "get_system_architecture",
    "get_storage_stats",
]