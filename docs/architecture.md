# Architecture – Stock Lakehouse AI

> **Ngày cập nhật:** 02/10/2026
> **File này:** Mô tả tổ chức code, vai trò từng thư mục/file, và luồng dữ liệu end-to-end.

---

## Mục lục

1. [Tổng quan cấu trúc](#1-tổng-quan-cấu-trúc)
2. [Luồng dữ liệu end-to-end](#2-luồng-dữ-liệu-end-to-end)
3. [Thư mục `app/` — chi tiết từng module](#3-thư-mục-app--chi-tiết-từng-module)
   - [`app/agent/` — AI Agent + Tool registry](#appagent--ai-agent--tool-registry)
   - [`app/api/` — FastAPI REST endpoints](#appapi--fastapi-rest-endpoints)
   - [`app/backtesting/` — Backtest engine + strategies](#appbacktesting--backtest-engine--strategies)
   - [`app/core/` — Config, constants, exceptions, logging](#appcore--config-constants-exceptions-logging)
   - [`app/database/` — SQLAlchemy ORM + repositories](#appdatabase--sqlalchemy-orm--repositories)
   - [`app/data_sources/` — External data providers](#appdata_sources--external-data-providers)
   - [`app/features/` — Feature engineering (Gold layer)](#appfeatures--feature-engineering-gold-layer)
   - [`app/forecasting/` — ML models (LR/ARIMA/LSTM)](#appforecasting--ml-models-lrarimalstm)
   - [`app/indicators/` — Technical indicators (SMA/EMA/RSI/MACD/BB)](#appindicators--technical-indicators)
   - [`app/lakehouse/` — Medallion layers + Iceberg](#applakehouse--medallion-layers--iceberg)
   - [`app/pipelines/` — Pipeline orchestrator](#apppipelines--pipeline-orchestrator)
   - [`app/schemas/` — Pydantic request/response models](#appschemas--pydantic-requestresponse-models)
   - [`app/services/` — Application services](#appservices--application-services)
   - [`app/streaming/` — Kafka + WebSocket (real-time)](#appstreaming--kafka--websocket-real-time)
4. [Đường dẫn import chuẩn](#4-đường-dẫn-import-chuẩn)
5. [Database schema](#5-database-schema)
6. [Docker services](#6-docker-services)

---

## 1. Tổng quan cấu trúc

```
stock-lakehouse-ai/
├── backend/
│   ├── app/                          # Mã nguồn chính (FastAPI)
│   │   ├── agent/                     # AI Agent (Gemini / local tool router)
│   │   ├── api/                       # FastAPI router + endpoints
│   │   ├── backtesting/               # Backtest engine
│   │   ├── core/                      # Config, constants, exceptions, logging
│   │   ├── database/                  # SQLAlchemy ORM + repositories
│   │   ├── data_sources/              # Providers (yfinance / Finnhub / SSI / ...)
│   │   ├── features/                  # Feature engineering
│   │   ├── forecasting/               # ML models
│   │   ├── indicators/               # Technical indicators
│   │   ├── lakehouse/               # Bronze / Silver / Gold + Iceberg
│   │   ├── pipelines/               # Pipeline orchestrator
│   │   ├── schemas/                 # Pydantic models
│   │   ├── services/                 # Application services
│   │   └── streaming/                # Kafka + WebSocket
│   ├── scripts/                     # CLI scripts (ingest, train, backtest, agent)
│   └── tests/                       # pytest tests
├── frontend/                         # React 18 + Vite + TypeScript + TailwindCSS
├── docs/                            # Tài liệu (PROGRESS_LAKEHOUSE.md, ...)
├── docker-compose.yml               # 4 service: MySQL, MinIO, Iceberg REST, Kafka
└── .env                            # Config runtime
```

---

## 2. Luồng dữ liệu end-to-end

```
┌──────────────────────────────────────────────────────────────────────┐
│                      EXTERNAL DATA SOURCES                            │
│  yfinance · Finnhub · Alpha Vantage · SSI iBoard · Web Scraper     │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  app/data_sources/         DataSourceFactory + MultiSourceProvider     │
│  (17 provider files)       Failover chain · Lazy import             │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  app/lakehouse/bronze.py  BRONZE LAYER                              │
│  • Schema validation   • Partition (symbol/year/month)               │
│  • Append-only        • Dedup (keep=last)                          │
│  • Lineage JSON       • StorageBackend abstraction                 │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  app/lakehouse/silver.py  SILVER LAYER                              │
│  • Timezone → UTC    • Type coercion                              │
│  • Missing check     • Invalid OHLC (high<low, high<open...)      │
│  • Duplicate check   • Negative volume                            │
│  • _errors/          • _quality.json                             │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  app/lakehouse/gold.py   GOLD LAYER  ←  app/features/                │
│  • SMA/EMA (5,10,20,50)   • RSI(14)                             │
│  • MACD(12,26,9)          • Bollinger Bands(20,±2σ)            │
│  • Advanced: ATR, ADX, Supertrend, Ichimoku, Stochastic, MFI      │
│  • Price: return, log_return, lag, rolling_std                    │
│  • Targets: shift(-1) ← NO LEAKAGE                                │
│  • Candlestick patterns, volume profile, composite signals          │
│  • Market regime (bull/bear/neutral)                             │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
 Technical Analysis   Forecasting      Backtesting         AI Agent
 (app/api/)          (app/forecasting/)  (app/backtesting/)  (app/agent/)
 (Recharts)           (LR/ARIMA/LSTM)    (MA Cross/RSI)    (Gemini Free)

  ┌──────────┬──────────┬──────────┬──────────────┐
  ▼          ▼          ▼          ▼              ▼
FastAPI      PyTorch    scikit     statsmodels    React UI
REST        LSTM        Linear     ARIMA          (Vite)
            Regression  Reg
```

---

## 3. Thư mục `app/` — chi tiết từng module

---

### `app/agent/` — AI Agent + Tool registry

| File | Dòng | Mô tả |
|------|-------|--------|
| `agent.py` | 198 | AI Agent orchestrator — chọn Gemini Free hoặc local tool router |
| `llm_client.py` | 183 | Gemini / OpenAI adapter — unified interface |
| `tool_registry.py` | 136 | Wire 14+ tools vào OpenAI function-calling format |
| `prompts.py` | 11 | System prompt cho Agent |
| `tools/stock_tools.py` | 159 | **Thực thi**: query_stock_data, get_market_summary, calculate_indicators, forecast_stock, compare_models, run_backtest |
| `tools/news_tools.py` | 90 | News/sentiment wrappers |
| `tools/fundamental_tools.py` | 94 | Fundamental metrics wrappers |
| `tools/walkforward_tools.py` | 39 | Walk-forward validation wrapper |

**Cách hoạt động:**
1. User gửi câu hỏi → `Agent.process()` (hoặc `/api/v1/agent/ask` endpoint)
2. Nếu có `GEMINI_API_KEY` → `LLMClient` gọi Gemini Free API
3. Gemini trả tool_calls → `tool_registry.execute_tool()` gọi đúng hàm
4. Kết quả tool trả về Gemini → Gemini tổng hợp câu trả lời cuối
5. Nếu không có API key → Local tool router (pattern matching câu hỏi → gọi tool trực tiếp)

---

### `app/api/` — FastAPI REST endpoints

| File | Dòng | Endpoint | Mô tả |
|------|-------|---------|--------|
| `v1/router.py` | 14 | — | Gộp tất cả sub-routers |
| `v1/endpoints/health.py` | 116 | `/health` | System health check |
| `v1/endpoints/data.py` | 186 | `/data/*` | Ingest stock/fundamental/news/macro |
| `v1/endpoints/pipeline.py` | 223 | `/pipeline/*` | Run Bronze→Silver→Gold |
| `v1/endpoints/stocks.py` | 52 | `/stocks/*` | Stock OHLCV data |
| `v1/endpoints/indicators.py` | 31 | `/indicators/*` | Technical indicators |
| `v1/endpoints/forecasting.py` | 29 | `/forecast/*` | Train/predict models |
| `v1/endpoints/backtesting.py` | 23 | `/backtest/*` | Run backtest |
| `v1/endpoints/market.py` | 161 | `/market/*` | Market summary, indices |
| `v1/endpoints/agent.py` | 23 | `/agent/*` | Chat với AI Agent |
| `v1/endpoints/dashboard.py` | 14 | `/dashboard/*` | Dashboard summary |

---

### `app/backtesting/` — Backtest engine + strategies

| File | Dòng | Mô tả |
|------|-------|--------|
| `engine.py` | 141 | Backtest engine — loop qua dữ liệu, sinh Trade objects |
| `metrics.py` | 63 | Tính Return, Sharpe, Win Rate, Max Drawdown, Profit Factor |
| `portfolio.py` | 61 | Portfolio management — equity, position sizing |
| `trade.py` | 16 | Trade object — entry/exit price, P&L |
| `strategy_base.py` | 12 | Abstract base cho strategy |
| `strategies/ma_crossover.py` | 18 | SMA(20) cắt SMA(50) → signal |
| `strategies/rsi_strategy.py` | 20 | RSI < 30 → long, RSI > 70 → short |
| `walk_forward.py` | 375 | Walk-forward analysis — nhiều fold train/test |

---

### `app/core/` — Config, constants, exceptions, logging

| File | Dòng | Mô tả |
|------|-------|--------|
| `config.py` | 149 | `Settings` class — đọc `.env`, tất cả config runtime. Singleton qua `@lru_cache`. |
| `constants.py` | 740+ | `GLOBAL_SYMBOLS` (958 ticker đa quốc gia), `SUPPORTED_SYMBOLS` (621 US), `MARKET_INDEXES`, `CRYPTO_SYMBOLS`, `OHLCV_COLUMNS`, feature columns, split ratios |
| `exceptions.py` | 44 | Custom exceptions: `DataSourceError`, `StorageError`, `ModelTrainingError`, … |
| `logging_config.py` | 39 | JSON structured logging qua `structlog` |
| `security.py` | 14 | JWT helpers (reserved for future auth) |
| `seeding.py` | 20 | `set_global_seed(42)` cho reproducibility |

**`config.py` đọc từ đâu:**
```python
# .env ở root project
STORAGE_BACKEND=minio           # hoặc "local"
DATA_SOURCE=multi_source        # yfinance | finnhub | ssi_vn | multi_source
GEMINI_API_KEY=<key>           # optional, fallback = local tool router
```

---

### `app/database/` — SQLAlchemy ORM + repositories

| File | Dòng | Mô tả |
|------|-------|--------|
| `base.py` | 4 | `DeclarativeBase` cho SQLAlchemy |
| `session.py` | 63 | `get_db()` generator, `check_database_connection()` |
| `models/user.py` | 18 | Bảng `users` |
| `models/pipeline_run.py` | 19 | Bảng `pipeline_runs` |
| `models/model_run.py` | 26 | Bảng `model_runs` |
| `models/backtest_run.py` | 24 | Bảng `backtest_runs` |
| `models/agent_conversation.py` | 17 | Bảng `agent_conversations` |
| `repositories/*.py` | — | CRUD cho từng model |

---

### `app/data_sources/` — External data providers

> **Sau khi refactor (02/10/2026):** Gốc 17 file, đã xóa 4 file duplicate, còn **13 file** gồm:

| File | Dòng | Mô tả |
|------|-------|--------|
| `base.py` | 23 | Abstract `StockDataProvider` — contract bắt buộc 3 method |
| `factory.py` | 85 | `get_data_provider(name)` — factory pattern theo `DATA_SOURCE` env |
| `multi_source.py` | 111 | Failover chain — thử nhiều provider → lấy cái đầu có data |
| `yfinance_python_provider.py` | 256 | Provider chính cho US stocks — dùng package `yfinance` |
| `finnhub_provider.py` | 235 | Finnhub REST + news + profile |
| `alpha_vantage_provider.py` | 114 | Alpha Vantage REST |
| `ssi_vn_provider.py` | 198 | SSI iBoard public API — 53 mã VN (HOSE/HNX/UPCOM) |
| `web_scraper_provider.py` | 214 | CafeF scrape + Yahoo HTTP fallback |
| `enhanced_fundamental_provider.py` | 326 | P/E, P/B, ROE, ROA, debt/equity, … |
| `enhanced_news_sentiment_provider.py` | 507 | Tin tức + sentiment scoring (LLM-based) |
| `macro_provider.py` | 399 | USD/VND, gold, oil, CPI, interest rate |
| `market_index_provider.py` | 163 | ^GSPC (S&P 500), ^DJI, ^IXIC |
| `orderbook_provider.py` | 239 | Bid/ask order book |

**Factory chọn provider:**
```python
from app.data_sources import get_data_provider
provider = get_data_provider()        # theo DATA_SOURCE trong .env
provider = get_data_provider("yfinance")  # override

# Nếu yfinance fail → MultiSourceProvider tự thử Finnhub → Alpha Vantage → Web Scraper
```

---

### `app/features/` — Feature engineering (Gold layer)

| File | Dòng | Mô tả |
|------|-------|--------|
| `feature_engineering.py` | 82 | `build_gold_features()` — orchestestrator, idempotent (strip cột cũ trước khi tính) |
| `technical_features.py` | 7 | Gọi `add_indicators()` |
| `price_features.py` | 22 | return, log_return, lag, rolling_std 20 ngày |
| `target_features.py` | 16 | `shift(-1)` cho target (NO LEAKAGE) |
| `advanced_features.py` | 427 | ATR, ADX, Stochastic, CCI, Williams%R, Supertrend, Ichimoku, VWAP, MFI, candlestick patterns |
| `macro_features.py` | 156 | Market regime (bull/bear/neutral), correlation features |

**Luồng tính feature:**
```python
from app.features import build_gold_features

gold = build_gold_features(silver_frame)
# Tự strip cột derived cũ → idempotent
# Tự xử lý từng symbol riêng (groupby)
# Rolling window NaN ở 50 dòng đầu → bình thường
```

---

### `app/forecasting/` — ML models (LR/ARIMA/LSTM)

| File | Dòng | Mô tả |
|------|-------|--------|
| `base.py` | 30 | `BaseForecastModel` abstract class |
| `linear_regression.py` | 67 | Linear Regression (sklearn) |
| `arima.py` | 72 | ARIMA (statsmodels) |
| `lstm.py` | 219 | LSTM (PyTorch, CPU) |
| `lstm_network.py` | 28 | `nn.Module` definition |
| `trainer.py` | 137 | Training loop chung |
| `predictor.py` | 127 | Prediction wrapper |
| `preprocessing.py` | 40 | MinMaxScaler, train/test split theo thời gian |
| `evaluator.py` | 42 | MAE, RMSE, MAPE, Directional Accuracy |
| `dataset.py` | 21 | SequenceDataset cho LSTM |
| `model_registry.py` | 61 | Registry đăng ký model |

---

### `app/indicators/` — Technical indicators (pure Pandas)

| File | Dòng | Công thức |
|------|-------|-----------|
| `sma.py` | 8 | `series.rolling(20).mean()` |
| `ema.py` | 8 | `series.ewm(span=12).mean()` — Wilder smoothing |
| `rsi.py` | 19 | RSI = 100 - 100/(1+RS), RS = avg_gain/avg_loss |
| `macd.py` | 23 | MACD=EMA12-EMA26, Signal=EMA9(MACD), Hist=MACD-Signal |
| `bollinger.py` | 23 | Upper=SMA+2σ, Middle=SMA, Lower=SMA-2σ |
| `service.py` | 94 | `add_indicators()` — gọi tất cả indicator, idempotent |

**Tất cả đều nhận `pd.Series` và trả về `pd.Series` hoặc `pd.DataFrame`.**

---

### `app/lakehouse/` — Medallion layers + Iceberg

Đây là **module lớn nhất**, 14 file:

| File | Dòng | Mô tả |
|------|-------|--------|
| `storage_base.py` | 43 | Abstract `StorageBackend` — 8 method bắt buộc |
| `storage_factory.py` | 22 | `get_storage_backend()` — tự fallback khi MinIO chết |
| `local_storage.py` | 71 | Ghi Parquet xuống `backend/data/{bronze,silver,gold}/` |
| `minio_storage.py` | 114 | Ghi Parquet lên MinIO bucket |
| `parquet_manager.py` | 24 | `split_by_partition()` — Hive-style path |
| `iceberg_manager.py` | 633 | Iceberg REST → time travel, schema evolution, snapshot |
| `spark_session.py` | 31 | Lazy Spark session (bật khi `USE_SPARK=true`) |
| `bronze.py` | 98 | `BronzeLayer` — append-only, lineage, dedupe |
| `silver.py` | 145 | `SilverLayer` — OHLC validation, `_errors/`, quality |
| `gold.py` | 53 | `GoldLayer` — gọi `build_gold_features()` |
| `gold_features.py` | 152 | `GoldFeaturesLayer` — sentiment/macro/index aggregate |
| `news_silver.py` | 82 | Schema riêng cho tin tức (symbol, title, content, sentiment) |
| `fundamentals_silver.py` | 98 | Schema riêng cho P/E, ROE, debt/equity |
| `pipeline.py` | 394 | `LakehousePipeline` — multi-symbol orchestrator |

**Storage abstraction:**
```
                    get_storage_backend()
                          │
         ┌─────────────────┴─────────────────┐
         ▼                                      ▼
  LocalStorageBackend                  MinioStorageBackend
  (dev, không Docker)                  (prod, có Docker)
  data/bronze/                         stock-bronze bucket
  data/silver/                         stock-silver bucket
  data/gold/                           stock-gold bucket
```

---

### `app/pipelines/` — Pipeline orchestrator

| File | Dòng | Mô tả |
|------|-------|--------|
| `orchestrator.py` | 320 | **SINGLE ENTRY POINT** — gộp 7 file cũ. Chứa: `ingest_symbol`, `validate_ohlc_frame`, `transform_to_silver`, `build_quality_report`, `assert_quality_passed`, `build_gold_layer`, `run_symbol_pipeline` |

**Cách dùng:**
```python
from app.pipelines import run_symbol_pipeline

# Chạy đầy đủ 3 tầng cho 1 mã
result = run_symbol_pipeline("AAPL", interval="1d")
# result = {"status": "success", "records_processed": 2500, ...}

# Hoặc chỉ ingest Bronze
result = run_symbol_pipeline("VCB", ingest=True, skip_silver=True, skip_gold=True)
```

---

### `app/schemas/` — Pydantic request/response models

| File | Dòng | Mô tả |
|------|-------|--------|
| `common.py` | 17 | `ok()` helper — wrap response |
| `stock.py` | 22 | OHLCV response |
| `indicator.py` | 17 | Indicator response |
| `forecasting.py` | 20 | Forecast request/response |
| `backtesting.py` | 17 | Backtest request/response |
| `agent.py` | 7 | Agent request/response |
| `dashboard.py` | 5 | Dashboard response |

---

### `app/services/` — Application services

| File | Dòng | Mô tả |
|------|-------|--------|
| `data_ingestion_service.py` | 307 | Batch ingest stock/fundamental/news/macro |
| `crawler_service.py` | 124 | Background crawler (threading, gọi từ `main.py` startup) |
| `unified_streaming_pipeline.py` | 321 | Integration tất cả nguồn + Kafka |
| `market_service.py` | 130 | Market summary + synthetic fallback khi lakehouse trống |
| `indicator_service.py` | 73 | Indicator computation |
| `forecasting_service.py` | 95 | Train + predict |
| `backtest_service.py` | 122 | Run backtest |
| `pipeline_service.py` | 33 | Run pipeline + lưu vào MySQL |
| `dashboard_service.py` | 94 | Dashboard summary (top movers, hot sectors) |
| `agent_service.py` | 56 | Chat với AI Agent |

---

### `app/streaming/` — Kafka + WebSocket (real-time)

| File | Dòng | Mô tả |
|------|-------|--------|
| `finnhub_websocket.py` | 252 | Finnhub WebSocket client — auto-reconnect, PING keepalive |
| `kafka_producer.py` | 382 | `StockKafkaProducer` — publish OHLCV raw → Kafka topic |
| `kafka_consumer.py` | 339 | `StockKafkaConsumer` — consume → Lakehouse |
| `stream_publisher.py` | 272 | `StreamPublisher` — gom tick thành 1s candle → Kafka |

**Luồng real-time:**
```
Finnhub WebSocket
  → StreamPublisher (1s candle agg)
  → Kafka topic "stock-ohlcv-raw"
  → KafkaConsumer
  → Bronze → Silver → Gold
```

---

## 4. Đường dẫn import chuẩn

```python
# Data providers
from app.data_sources import get_data_provider
from app.data_sources import YFinancePythonProvider, FinnhubProvider, SSIVNProvider

# Lakehouse
from app.lakehouse import BronzeLayer, SilverLayer, GoldLayer
from app.lakehouse import LocalStorageBackend, MinioStorageBackend, get_storage_backend
from app.lakehouse import LakehousePipeline

# Pipeline
from app.pipelines import run_symbol_pipeline

# Features
from app.features import build_gold_features
from app.indicators import add_indicators

# Forecasting
from app.forecasting import LSTMForecastModel

# Backtesting
from app.backtesting import BacktestEngine
```

---

## 5. Database schema

Bảng `stock_lakehouse` trong MySQL 8:

| Bảng | Mô tả |
|------|--------|
| `users` | Tài khoản user |
| `pipeline_runs` | Lịch sử chạy pipeline |
| `model_runs` | Lịch sử train model |
| `backtest_runs` | Lịch sử backtest |
| `agent_conversations` | Lịch sử chat AI Agent |

---

## 6. Docker services

| Service | Image | Port | Vai trò |
|---------|-------|------|---------|
| `mysql` | mysql:8.4 | 3307 | Metadata DB |
| `minio` | quay.io/minio/minio | 9000/9001 | Object storage (S3-compatible) |
| `iceberg-rest` | tabulario/iceberg-rest:0.9.0 | 8181 | Iceberg REST Catalog |
| `kafka` | apache/kafka:3.8.0 | 9092/9094 | Streaming backbone |

**Chạy:**
```powershell
docker compose up -d
```

---

## Change log refactor (02/10/2026)

Những gì đã dọn:

- **Xóa 3 stub file rỗng** (`agent/tools/backtest_tools.py`, `forecast_tools.py`, `indicator_tools.py`) — implement thật nằm trong `stock_tools.py`
- **Xóa 3 duplicate data provider** cũ: `fundamental_provider.py`, `news_sentiment_provider.py`, `yfinance_provider.py`
- **Xóa `services/stream/kafka_consumer.py`** (dead code — không ai dùng, xóa luôn thư mục `services/stream/`)
- **Gộp 7 file trong `app/pipelines/`** thành 1 file `orchestrator.py` duy nhất
- **Factory đơn giản hóa**: bỏ `yfinance_direct`, còn lại `yfinance`, `finnhub`, `alpha_vantage`, `web_scraper`, `ssi_vn`, `multi_source`
- **Tất cả import đã verify** — smoke test + pytest passed
