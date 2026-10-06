# Tech Stack -> Implementation Matrix

Mỗi công nghệ được liệt kê trong đồ án phải có code/implementation thật, không
phải chỉ config rỗng. Bảng dưới đây map trực tiếp từng công nghệ sang file
Python / config chịu trách nhiệm implementation.

> Yêu cầu dữ liệu: **>= 5 năm x >= 60 symbols x 1d interval** = >= 75,000 rows OHLCV (Bronze).

---

## Tech stack tổng quan

| Tầng | Công nghệ | Cài qua |
|------|-----------|---------|
| Backend API | Python 3.11, FastAPI, Pydantic v2, Uvicorn | `backend/requirements.txt` |
| ORM / Migration | SQLAlchemy 2, Alembic | `backend/requirements.txt` |
| Metadata DB | MySQL 8 | `docker-compose.yml` (`mysql` service) |
| Object Storage | MinIO (S3-compatible) | `docker-compose.yml` (`minio` service) |
| Lakehouse format | Apache Parquet + Apache Iceberg (REST) | `docker-compose.yml` (`iceberg-rest` service) |
| Streaming | Apache Kafka 3.8 (KRaft) | `docker-compose.yml` (`kafka` service) |
| ML | scikit-learn, statsmodels (ARIMA), PyTorch (LSTM) | `backend/requirements.txt` |
| AI Agent | Gemini Free API (`gemini-2.0-flash-exp`) | `.env` -> `GEMINI_API_KEY` |
| Frontend | React 18, Vite 5, TypeScript, TailwindCSS, TanStack Query, Recharts, Lucide | `frontend/package.json` |

---

## Data Sources (multi-provider, $0 budget)

| Provider              | File / Implementation                                                                          | Ghi chú |
|-----------------------|------------------------------------------------------------------------------------------------|---------|
| **yfinance package**  | `backend/app/data_sources/yfinance_python_provider.py`                                        | Primary khi `DATA_SOURCE=yfinance`; `yfinance>=1.0` + `curl_cffi` để bypass Yahoo TLS fingerprint block. Hỗ trợ 1m/5m/15m/1h/1d + news. |
| **yfinance HTTP**     | `backend/app/data_sources/yfinance_provider.py`                                               | Fallback khi thiếu package `yfinance`. |
| **Finnhub Free**      | `backend/app/data_sources/finnhub_provider.py`                                                | OHLCV + news + company profile. Tôn trọng giới hạn Free tier (60 req/min). |
| **Alpha Vantage**     | `backend/app/data_sources/alpha_vantage_provider.py`                                          | Daily + intraday (25 req/day free). |
| **SSI iBoard (VN)**   | `backend/app/data_sources/ssi_vn_provider.py`                                                 | HOSE/HNX/UPCOM, public API. |
| **Web scraper**       | `backend/app/data_sources/web_scraper_provider.py`                                            | CafeF (VN) + Yahoo HTTP fallback. |
| **Macro provider**    | `backend/app/data_sources/macro_provider.py`                                                  | USD/VND, gold, oil (Vietcombank, SJC, EIA). |
| **Fundamental**       | `backend/app/data_sources/fundamental_provider.py`, `enhanced_fundamental_provider.py`        | Revenue/EPS/ROE/P/E cho VN stocks. |
| **News sentiment**    | `backend/app/data_sources/news_sentiment_provider.py`, `enhanced_news_sentiment_provider.py`   | Crawl + lexicon VN/EN. |
| **Order book**        | `backend/app/data_sources/orderbook_provider.py`                                              | Snapshot orderbook. |
| **Market indexes**    | `backend/app/data_sources/market_index_provider.py`                                           | ^GSPC, ^DJI, ^IXIC. |
| **Multi-source failover** | `backend/app/data_sources/multi_source.py`                                                | Auto failover chain. |

---

## Lakehouse (Medallion Architecture)

| Layer       | File                                                                       | Mô tả |
|-------------|----------------------------------------------------------------------------|-------|
| **Bronze**  | `backend/app/lakehouse/bronze.py`, `parquet_manager.py`, `storage_base.py` | Append raw OHLCV, partition theo `symbol/year/month`, dedupe, lineage tracking (`_lineage.json`). |
| **Silver**  | `backend/app/lakehouse/silver.py`                                          | Clean OHLCV (engine = **Pandas**), validate timestamp/OHLC/volume, write `_errors/` cho invalid rows. |
| **Gold**    | `backend/app/lakehouse/gold.py` + `app/features/*`                          | Build features không look-ahead (technical, price, target, advanced, candlestick, macro). |
| **Pipeline**| `backend/app/lakehouse/pipeline.py`                                        | `LakehousePipeline.run(symbols)` orchestrates Bronze -> Silver -> Gold. |
| **Iceberg** | `backend/app/lakehouse/iceberg_manager.py`                                 | Schema Bronze/Silver/Gold, REST catalog, time-travel queries. |
| **Storage** | `backend/app/lakehouse/storage_factory.py`, `minio_storage.py`, `local_storage.py` | MinIO (S3-compatible) + local fallback. |

> Engine transform là **Pandas** (in-process). Không dùng Spark - giữ hạ tầng Docker tối giản (4 service).

---

## Streaming (Near-real-time)

| Component             | File                                                                  | Vai trò |
|-----------------------|----------------------------------------------------------------------|---------|
| **Finnhub WebSocket** | `backend/app/streaming/finnhub_websocket.py`                          | Auto-reconnect + PING + per-second OHLCV aggregation. |
| **Stream Publisher**  | `backend/app/streaming/stream_publisher.py`                           | WS -> 1s bars -> Kafka topic `stock-ohlcv-raw`. |
| **Kafka Producer**    | `backend/app/streaming/kafka_producer.py`                             | Publish OHLCV/alerts. |
| **Kafka Consumer**    | `backend/app/streaming/kafka_consumer.py`                             | Subscribe -> Bronze/Silver/Gold. |
| **Aggregator**        | `backend/app/streaming/kafka_consumer.py` (`RealTimeAggregator`)      | 1m -> 5m/15m/1h/1d resample. |
| **CLI runner**        | `backend/scripts/run_stream_publisher.py`, `run_stream_consumer.py`   | CLI chạy standalone. |

---

## ML / Forecasting

| Model                | File                                                  | Implementation |
|----------------------|-------------------------------------------------------|----------------|
| **Linear Regression**| `backend/app/forecasting/linear_regression.py`        | sklearn pipeline. |
| **ARIMA**            | `backend/app/forecasting/arima.py`                    | statsmodels SARIMAX. |
| **LSTM (PyTorch)**   | `backend/app/forecasting/lstm.py`, `lstm_network.py`  | 2-layer LSTM với early stopping. |
| **Training orchestrator** | `backend/app/forecasting/trainer.py`              | `train_model(symbol, model_name)`. |
| **Preprocessing**    | `backend/app/forecasting/preprocessing.py`            | chronological split (no leakage). |
| **Dataset**          | `backend/app/forecasting/dataset.py`                  | Sliding-window sequence dataset cho LSTM. |
| **Evaluator**        | `backend/app/forecasting/evaluator.py`                | MAE/RMSE/MAPE/Directional accuracy. |
| **Registry**         | `backend/app/forecasting/model_registry.py`           | Filesystem registry. |
| **Predictor**        | `backend/app/forecasting/predictor.py`                | Production inference. |

---

## Features (Gold layer)

| Module                | File                                                                              | Output |
|-----------------------|-----------------------------------------------------------------------------------|--------|
| **Technical**         | `backend/app/features/technical_features.py` + `app/indicators/{sma,ema,rsi,macd,bollinger}.py` | SMA/EMA/RSI/MACD/Bollinger. |
| **Price**             | `backend/app/features/price_features.py`                                          | Returns, log-returns, ranges. |
| **Target**            | `backend/app/features/target_features.py`                                         | Next-day close/return/direction (no leakage). |
| **Advanced**          | `backend/app/features/advanced_features.py`                                       | ATR, ADX, momentum, volatility, candlestick patterns. |
| **Macro + Regime**    | `backend/app/features/macro_features.py`                                          | USD/VND, gold, oil, regime classification (bull/bear x high/low vol). |
| **Composite signals** | `backend/app/features/advanced_features.py` (`add_composite_signals`)            | Buy/sell/hold scores. |
| **Volume profile**    | `backend/app/features/advanced_features.py`                                       | VPVR, value area. |

---

## Backtesting

| Component           | File                                                  | Vai trò |
|---------------------|-------------------------------------------------------|---------|
| **Engine**          | `backend/app/backtesting/engine.py`                   | Event-driven, next-bar execution. |
| **Portfolio**       | `backend/app/backtesting/portfolio.py`                | Cash, positions, equity curve. |
| **Trade**           | `backend/app/backtesting/trade.py`                    | Trade records. |
| **Metrics**         | `backend/app/backtesting/metrics.py`                  | Sharpe, max drawdown, win rate, profit factor. |
| **Strategies**      | `backend/app/backtesting/strategies/{ma_crossover,rsi_strategy}.py` | Implementations. |
| **Walk-forward**    | `backend/app/backtesting/walk_forward.py`             | Rolling-window validation. |
| **CLI runners**     | `backend/scripts/run_backtest.py`, `run_walk_forward.py` | CLI invocation. |

---

## AI Agent (Tool-calling + Gemini)

| Component             | File                                          | Vai trò |
|-----------------------|-----------------------------------------------|---------|
| **Agent core**        | `backend/app/agent/agent.py`                  | Orchestrator (Gemini + local router fallback). |
| **LLM client**        | `backend/app/agent/llm_client.py`             | OpenAI-compatible streaming (Gemini, OpenAI). |
| **Prompts**           | `backend/app/agent/prompts.py`                | System instructions. |
| **Tool registry**     | `backend/app/agent/tool_registry.py`          | 9+ tool definitions. |
| **Stock tools**       | `backend/app/agent/tools/stock_tools.py`      | Latest price, history, compare. |
| **Indicator tools**   | `backend/app/agent/tools/indicator_tools.py`  | RSI/MACD/SMA queries. |
| **Forecast tools**    | `backend/app/agent/tools/forecast_tools.py`   | LR/ARIMA/LSTM predictions. |
| **Backtest tools**    | `backend/app/agent/tools/backtest_tools.py`   | MA crossover/RSI backtests. |
| **Walk-forward tools**| `backend/app/agent/tools/walkforward_tools.py`| Walk-forward validation. |
| **News tools**        | `backend/app/agent/tools/news_tools.py`       | News headlines. |
| **Fundamental tools** | `backend/app/agent/tools/fundamental_tools.py`| EPS/P/E ratios. |
| **Service**           | `backend/app/services/agent_service.py`       | Persist conversations vào MySQL. |
| **CLI runner**        | `backend/scripts/run_agent.py`                | Headless agent test. |

---

## Frontend

| Component             | File                                                  | Vai trò |
|-----------------------|-------------------------------------------------------|---------|
| **API entrypoint**    | `backend/app/main.py`                                 | FastAPI app, lifespan, CORS, exception handlers. |
| **App shell**         | `frontend/src/App.tsx`                                | Routes + layout. |
| **API client**        | `frontend/src/api/*.ts`                               | Axios wrapper gọi `/api/v1`. |
| **Dashboard page**    | `frontend/src/pages/Dashboard.tsx`                    | Giá + indicator + chart. |
| **Market Data page**  | `frontend/src/pages/MarketData.tsx`                   | OHLCV chart + table. |
| **Indicators page**   | `frontend/src/pages/Indicators.tsx`                   | Technical analysis. |
| **Forecast page**     | `frontend/src/pages/Forecasting.tsx`                  | Train + predict 3 model. |
| **Backtest page**     | `frontend/src/pages/Backtesting.tsx`                  | MA/RSI strategy + metrics. |
| **Agent page**        | `frontend/src/pages/Agent.tsx`                        | Chat với AI Agent. |
| **Status page**       | `frontend/src/pages/SystemStatus.tsx`                 | Health check tổng. |
| **Vite config**       | `frontend/vite.config.ts`                             | Proxy `/api/v1` -> `127.0.0.1:8000` (local dev). |
| **Env**               | `frontend/.env` (`VITE_API_BASE_URL`)                 | API base URL. |
| **Dockerfile**        | `frontend/Dockerfile`                                 | Multi-stage Vite build → nginx:alpine. |
| **Nginx config**      | `frontend/nginx.conf`                                 | SPA fallback + reverse-proxy `/api/*` → backend. |

---

## Orchestration / Scripts

| Component       | File                                                  | Vai trò |
|-----------------|-------------------------------------------------------|---------|
| **Schedule**    | `backend/scripts/schedule_batch.py`                   | Cron-like batch scheduling. |
| **Init DB**     | `backend/scripts/init_database.py`                    | CREATE DATABASE + Alembic upgrade head. |
| **Bootstrap**   | `backend/scripts/bootstrap_infrastructure.py`         | Tạo MinIO buckets + Kafka topics. |
| **Iceberg init**| `backend/scripts/init_iceberg_tables.py`               | Tạo Bronze/Silver/Gold Iceberg tables. |
| **Seed DB**     | `backend/scripts/seed_database.py`                    | (optional) seed dữ liệu test. |

---

## Data Scale

Với config mặc định (`scripts/ingest_historical.py --years 10`):

- **Lookback:** 3650 ngày (~10 năm daily bars).
- **Symbols:** 60+ US stocks + indexes + crypto + 53 VN stocks.
- **Total rows:** ~250.000 OHLCV rows cho mỗi ingestion run.
- **Storage:** Bronze (raw) + Silver (cleaned) + Gold (features) ~vài trăm MB Parquet trên MinIO.

---

## Scripts CLI (mỗi cái là implementation thật)

| Script                                     | Công nghệ                       | Vai trò |
|--------------------------------------------|---------------------------------|---------|
| `scripts/init_database.py`                 | SQLAlchemy + Alembic             | Tạo DB + chạy migrations |
| `scripts/bootstrap_infrastructure.py`      | MinIO + Kafka admin              | Tạo buckets + topics |
| `scripts/ingest_historical.py`             | yfinance/Finnhub/AlphaVantage    | REAL 10-năm OHLCV cho US+global symbols, Bronze->Silver->Gold |
| `scripts/ingest_vn.py`                     | SSI iBoard                       | 50+ cổ phiếu VN, Bronze->Silver->Gold + quality report |
| `scripts/init_iceberg_tables.py`           | pyiceberg                        | Tạo Bronze/Silver/Gold Iceberg tables |
| `scripts/run_pipeline.py`                  | LakehousePipeline                | Chạy Bronze->Silver->Gold cho 1 symbol đã có Bronze |
| `scripts/run_stream_publisher.py`          | websocket-client + kafka-python  | WS -> Kafka |
| `scripts/run_stream_consumer.py`           | kafka-python                     | Kafka -> Bronze/Silver/Gold |
| `scripts/train_models.py`                  | sklearn/statsmodels/torch        | Train LR/ARIMA/LSTM |
| `scripts/run_backtest.py`                  | BacktestEngine                   | Single backtest |
| `scripts/run_walk_forward.py`              | WalkForwardValidator             | Walk-forward validation |
| `scripts/run_indicators.py`                | IndicatorService                 | Compute indicators ad-hoc |
| `scripts/run_macro_features.py`            | MacroFeatureBuilder              | Compute macro + regime features |
| `scripts/run_agent.py`                     | StockAnalysisAgent               | Headless AI agent test |
| `scripts/transform_to_silver.py`           | Silver transform                 | Legacy batch transform |
| `scripts/rebuild_gold.py`                  | Gold feature builder             | Rebuild Gold cho symbols bị lỗi |

---

## Docker Services

| Service       | Image                          | Port (host)  | Mục đích |
|---------------|--------------------------------|--------------|----------|
| **mysql**     | `mysql:8.4`                    | 3307         | Metadata DB |
| **minio**     | `quay.io/minio/minio:latest`   | 9000, 9001   | Object storage + Console UI |
| **iceberg-rest** | `tabulario/iceberg-rest:0.9.0` | 8181       | Iceberg REST Catalog |
| **kafka**     | `apache/kafka:3.8.0` (KRaft)   | 9092, 9094   | Streaming backbone |
| **backend**   | `stock-lakehouse-backend:latest` (custom multi-stage) | 8000 | FastAPI + Uvicorn |
| **frontend**  | `stock-lakehouse-frontend:latest` (Vite + nginx) | 8081 | React SPA, proxies `/api/*` → `backend:8000` |

> Cả backend và frontend đều đã đóng gói Docker (multi-stage build). Chạy
> end-to-end bằng `docker compose up -d` từ thư mục repo, sau đó mở
> <http://localhost:8081>. Backend API trực tiếp tại <http://localhost:8000/api/v1/docs>.
