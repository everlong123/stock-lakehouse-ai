"""Functional smoke test - kiểm tra tất cả modules có import + chạy được không."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def test(label: str, fn) -> tuple[str, str, str]:
    """Run a test and return (label, status, message)."""
    try:
        msg = fn()
        return (label, "OK", msg)
    except Exception as e:
        return (label, "FAIL", f"{type(e).__name__}: {str(e)[:100]}")


results = []

# ── 1. Lakehouse (Bronze/Silver/Gold) ──────────────────────────────────────
def t1():
    from app.lakehouse import BronzeLayer, SilverLayer, GoldLayer
    b = BronzeLayer().read("AAPL")
    s = SilverLayer().read("AAPL")
    g = GoldLayer().read("AAPL")
    return f"Bronze={len(b)} Silver={len(s)} Gold={len(g)} cols={g.shape[1]}"
results.append(test("1. Lakehouse (Bronze/Silver/Gold)", t1))

# ── 2. Technical indicators ────────────────────────────────────────────────
def t2():
    from app.indicators.service import IndicatorService
    s = IndicatorService()
    rsi = s.calculate("AAPL", "rsi_14")
    return f"RSI sample = {rsi.iloc[-1,0]:.2f}" if not rsi.empty else "no data"
results.append(test("2. Technical Indicators", t2))

# ── 3. Forecasting (LSTM/ARIMA/LR/Predictor) ───────────────────────────────
def t3():
    from app.forecasting.lstm import LSTMModel
    from app.forecasting.arima import ARIMAForecaster
    from app.forecasting.linear_regression import LinearRegressionForecaster
    from app.forecasting.predictor import Predictor
    m = LSTMModel()
    n = sum(p.numel() for p in m.parameters())
    return f"LSTM={n} params | ARIMA ok | LR ok | Predictor ok"
results.append(test("3. Forecasting (LSTM/ARIMA/LR)", t3))

# ── 4. Backtesting engine + strategies ─────────────────────────────────────
def t4():
    from app.backtesting.engine import BacktestEngine
    from app.backtesting.strategies.ma_crossover import MACrossoverStrategy
    from app.backtesting.strategies.rsi_strategy import RSIStrategy
    from app.backtesting.walk_forward import WalkForwardValidator
    return "engine + 2 strategies + walk-forward"
results.append(test("4. Backtesting", t4))

# ── 5. AI Agent (LLM + tools) ──────────────────────────────────────────────
def t5():
    from app.agent.agent import StockAgent
    from app.agent.tool_registry import ToolRegistry
    from app.agent.tools.stock_tools import fetch_history
    return "StockAgent + ToolRegistry + stock_tools"
results.append(test("5. AI Agent", t5))

# ── 6. Streaming (Kafka + Finnhub WS) ──────────────────────────────────────
def t6():
    from app.streaming.kafka_producer import KafkaProducer
    from app.streaming.kafka_consumer import KafkaConsumer
    from app.streaming.finnhub_websocket import FinnhubWebSocketClient
    return "Kafka producer/consumer + Finnhub WS"
results.append(test("6. Streaming", t6))

# ── 7. Iceberg + Spark ─────────────────────────────────────────────────────
def t7():
    from app.lakehouse.iceberg_manager import IcebergManager
    from app.lakehouse.spark_session import get_spark_session
    return "Iceberg + Spark modules importable"
results.append(test("7. Iceberg + Spark", t7))

# ── 8. Data sources (10 providers) ─────────────────────────────────────────
def t8():
    from app.data_sources import (
        yfinance_python_provider, yahoo_http_provider, alpha_vantage_provider,
        finnhub_provider, stooq_provider, web_scraper_provider,
        multi_source, macro_provider, market_index_provider,
        ssi_vn_provider, enhanced_fundamental_provider, enhanced_news_sentiment_provider,
        orderbook_provider
    )
    return "13 data source modules"
results.append(test("8. Data sources (13 modules)", t8))

# ── 9. Database models ─────────────────────────────────────────────────────
def t9():
    from app.database.models.user import User
    from app.database.models.pipeline_run import PipelineRun
    from app.database.models.backtest_run import BacktestRun
    from app.database.models.model_run import ModelRun
    from app.database.models.agent_conversation import AgentConversation
    return "5 DB models"
results.append(test("9. Database models", t9))

# ── 10. Pipeline orchestrator ──────────────────────────────────────────────
def t10():
    from app.pipelines.orchestrator import run_symbol_pipeline, build_quality_report
    return "orchestrator ok"
results.append(test("10. Pipeline orchestrator", t10))

# ── 11. Features (technical / price / target / advanced / macro) ───────────
def t11():
    from app.features import (
        technical_features, price_features, target_features,
        advanced_features, macro_features, feature_engineering
    )
    return "6 feature modules"
results.append(test("11. Feature engineering (6 modules)", t11))

# ── 12. Schemas (Pydantic) ─────────────────────────────────────────────────
def t12():
    from app.schemas import (
        common, stock, dashboard, indicator,
        forecasting, backtesting, agent
    )
    return "7 schema modules"
results.append(test("12. Pydantic schemas (7 modules)", t12))

# ── 13. Services (market/data_ingestion/...) ─────────────────────────────────────
def t13():
    from app.services import (
        market_service, data_ingestion_service, indicator_service,
        dashboard_service, forecasting_service, backtest_service,
        agent_service, crawler_service, pipeline_service,
        unified_streaming_pipeline
    )
    return "10 service modules"
results.append(test("13. Services (10 modules)", t13))

# ── 14. API routers ────────────────────────────────────────────────────────
def t14():
    from app.api.v1.endpoints import (
        health, stocks, indicators, dashboard, market, pipeline,
        forecasting, backtesting, agent, data
    )
    return "10 routers"
results.append(test("14. API routers (10)", t14))


# ── Print results ──────────────────────────────────────────────────────────
OK = "\033[92m[OK]\033[0m"
NO = "\033[91m[!!]\033[0m"
ok_count = 0
fail_count = 0
for label, status, msg in results:
    sym = OK if status == "OK" else NO
    print(f"{sym} {label}: {msg}")
    if status == "OK":
        ok_count += 1
    else:
        fail_count += 1

print()
print(f"=== Summary: {ok_count} OK, {fail_count} FAIL ===")
sys.exit(0 if fail_count == 0 else 1)