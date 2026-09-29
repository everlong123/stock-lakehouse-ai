# Tech Stack → Implementation Matrix

Mỗi công nghệ được liệt kê trong đồ án phải có code/implementation thật, không
phải chỉ config rỗng. Bảng dưới đây map trực tiếp từng công nghệ sang file
Python chịu trách nhiệm implementation.

> Yêu cầu dữ liệu: **≥ 5 năm × ≥ 60 symbols × 1d interval** = ≥ 75,000 dòng OHLCV.

---

## Data Sources (multi-provider, $0 budget)

| Provider              | File / Implementation                                                                                | Ghi chú |
|-----------------------|------------------------------------------------------------------------------------------------------|---------|
| **yfinance package**  | `backend/app/data_sources/yfinance_python_provider.py`                                                | Ưu tiên khi `DATA_SOURCE=yfinance`; đã có sẵn package `yfinance>=0.2.40`. Hỗ trợ 1m/5m/15m/1h/1d + news. |
| **yfinance HTTP**     | `backend/app/data_sources/yfinance_provider.py`                                                      | Fallback khi thiếu package `yfinance`. |
| **Finnhub Free**      | `backend/app/data_sources/finnhub_provider.py`                                                       | Lấy OHLCV + news + company profile. Tôn trọng giới hạn Free tier. |
| **Alpha Vantage**     | `backend/app/data_sources/alpha_vantage_provider.py`                                                 | Daily + intraday. |
| **Web scraper**       | `backend/app/data_sources/web_scraper_provider.py`                                                   | CafeF (VN) + Yahoo HTTP fallback. |
| **Macro provider**    | `backend/app/data_sources/macro_provider.py`                                                         | USD/VND, gold, oil (Vietcombank, SJC, EIA). |
| **Fundamental**       | `backend/app/data_sources/fundamental_provider.py`, `enhanced_fundamental_provider.py`              | Revenue/EPS/ROE/P/E cho VN stocks. |
| **News sentiment**    | `backend/app/data_sources/news_sentiment_provider.py`, `enhanced_news_sentiment_provider.py`         | Crawl + lexicon VN/EN. |
| **Order book**        | `backend/app/data_sources/orderbook_provider.py`                                                     | Snapshot orderbook. |
| **Market indexes**    | `backend/app/data_sources/market_index_provider.py`                                                  | ^GSPC, ^DJI, ^IXIC. |
| **Multi-source failover** | `backend/app/data_sources/multi_source.py`                                                      | Tự động thử từng provider trong chain. |

## Lakehouse (Medallion Architecture)

| Layer       | File                                                                   | Mô tả |
|-------------|------------------------------------------------------------------------|-------|
| **Bronze**  | `backend/app/lakehouse/bronze.py`, `parquet_manager.py`, `storage_base.py` | Append raw OHLCV, partition theo `symbol/year/month`, dedupe, lineage tracking. |
| **Silver**  | `backend/app/lakehouse/silver.py`                                       | Clean OHLCV (Pandas **+ Spark**), validate timestamp/OHLC/volume, write `_errors/` cho invalid rows. |
| **Gold**    | `backend/app/lakehouse/gold.py` + `app/features/*`                     | Build features không look-ahead (technical, price, target, advanced, candlestick, macro). |
| **Pipeline**| `backend/app/lakehouse/pipeline.py`                                    | `LakehousePipeline.run(symbols)` orchestrates Bronze→Silver→Gold. |
| **Iceberg** | `backend/app/lakehouse/iceberg_manager.py`                             | Schema Bronze/Silver/Gold, REST catalog, time-travel queries. |
| **Storage** | `backend/app/lakehouse/storage_factory.py`, `minio_storage.py`, `local_storage.py` | MinIO (S3-compatible) + local fallback. |

## Streaming (Real-time)

| Component             | File                                                                  | Vai trò |
|-----------------------|----------------------------------------------------------------------|---------|
| **Finnhub WebSocket** | `backend/app/streaming/finnhub_websocket.py`                          | Auto-reconnect + PING + per-second OHLCV aggregation. |
| **Stream Publisher**  | `backend/app/streaming/stream_publisher.py`                           | WS → 1s bars → Kafka topic `stock-ohlcv-raw`. |
| **Kafka Producer**    | `backend/app/streaming/kafka_producer.py`                             | Publish OHLCV/alerts. |
| **Kafka Consumer**    | `backend/app/streaming/kafka_consumer.py`                             | Subscribe → Bronze/Silver/Gold. |
| **Aggregator**        | `backend/app/streaming/kafka_consumer.py` (`RealTimeAggregator`)      | 1m→5m/15m/1h/1d resample. |
| **CLI runner**        | `backend/scripts/run_stream_publisher.py`, `run_stream_consumer.py`   | CLI chạy standalone. |

## ML / Forecasting

| Model                | File                                                  | Implementation |
|----------------------|-------------------------------------------------------|----------------|
| **Linear Regression**| `backend/app/forecasting/linear_regression.py`        | sklearn pipeline. |
| **ARIMA**            | `backend/app/forecasting/arima.py`                     | statsmodels SARIMAX. |
| **LSTM (PyTorch)**   | `backend/app/forecasting/lstm.py`, `lstm_network.py`  | 2-layer LSTM với early stopping. |
| **Training orchestrator** | `backend/app/forecasting/trainer.py`              | `train_model(symbol, model_name)`. |
| **Preprocessing**    | `backend/app/forecasting/preprocessing.py`            | chronological split (no leakage). |
| **Dataset**          | `backend/app/forecasting/dataset.py`                  | Sliding-window sequence dataset cho LSTM. |
| **Evaluator**        | `backend/app/forecasting/evaluator.py`                 | MAE/RMSE/MAPE/Directional accuracy. |
| **Registry**         | `backend/app/forecasting/model_registry.py`           | Filesystem registry. |
| **Predictor**        `backend/app/forecasting/predictor.py`                 | Production inference. |

## Features (Gold layer)

| Module                | File                                              | Output |
|-----------------------|---------------------------------------------------|--------|
| **Technical**         | `backend/app/features/technical_features.py` + `app/indicators/{sma,ema,rsi,macd,bollinger}.py` | SMA/EMA/RSI/MACD/Bollinger. |
| **Price**             | `backend/app/features/price_features.py`           | Returns, log-returns, ranges. |
| **Target**            | `backend/app/features/target_features.py`          | Next-day close/return/direction (no leakage). |
| **Advanced**          | `backend/app/features/advanced_features.py`        | ATR, ADX, momentum, volatility, candlestick patterns. |
| **Macro + Regime**    | `backend/app/features/macro_features.py`           | USD/VND, gold, oil, regime classification (bull/bear × high/low vol). |
| **Composite signals** | `backend/app/features/advanced_features.py` (`add_composite_signals`) | Buy/sell/hold scores. |
| **Volume profile**    | `backend/app/features/advanced_features.py`        | VPVR, value area. |

## Backtesting

| Component           | File                                                  | Vai trò |
|---------------------|-------------------------------------------------------|---------|
| **Engine**          | `backend/app/backtesting/engine.py`                   | Event-driven, next-bar execution. |
| **Portfolio**       | `backend/app/backtesting/portfolio.py`                | Cash, positions, equity curve. |
| **Trade**           | `backend/app/backtesting/trade.py`                    | Trade records. |
| **Metrics**         | `backend/app/backtesting/metrics.py`                   | Sharpe, max drawdown, win rate, profit factor. |
| **Strategies**      | `backend/app/backtesting/strategies/{ma_crossover,rsi_strategy}.py` | Implementations. |
| **Walk-forward**    | `backend/app/backtesting/walk_forward.py`             | Rolling-window validation. |
| **CLI runners**     | `backend/scripts/run_backtest.py`, `run_walk_forward.py` | CLI invocation. |

## AI Agent (Tool-calling)

| Component             | File                                          | Vai trò |
|-----------------------|-----------------------------------------------|---------|
| **Agent core**        | `backend/app/agent/agent.py`                  | Orchestrator (OpenAI + fallback). |
| **LLM client**        | `backend/app/agent/llm_client.py`             | OpenAI streaming. |
| **Prompts**           | `backend/app/agent/prompts.py`                | System instructions. |
| **Tool registry**     | `backend/app/agent/tool_registry.py`          | 14+ tool definitions. |
| **Stock tools**       | `backend/app/agent/tools/stock_tools.py`      | Latest price, history, compare. |
| **Indicator tools**   | `backend/app/agent/tools/indicator_tools.py`  | RSI/MACD/SMA queries. |
| **Forecast tools**    | `backend/app/agent/tools/forecast_tools.py`   | LR/ARIMA/LSTM predictions. |
| **Backtest tools**    | `backend/app/agent/tools/backtest_tools.py`   | MA crossover/RSI backtests. |
| **Walk-forward tools**| `backend/app/agent/tools/walkforward_tools.py`| Walk-forward validation. |
| **News tools**        | `backend/app/agent/tools/news_tools.py`       | News headlines. |
| **Fundamental tools** | `backend/app/agent/tools/fundamental_tools.py`| EPS/P/E ratios. |
| **Service**           | `backend/app/services/agent_service.py`       | Persist conversations. |
| **CLI runner**        | `backend/scripts/run_agent.py`                | Headless agent test. |

## Orchestration

| Component       | File                                                  | Vai trò |
|-----------------|-------------------------------------------------------|---------|
| **Dagster**     | `dagster/dagster_definitions.py`                      | Pipeline as DAG (run trên local, vì image không public). |
| **Airflow**     | `dags/*.py`, `docker-compose.yml` (Airflow services)  | Optional orchestration via `apache/airflow:2.8.0`. |
| **Schedule**    | `backend/scripts/schedule_batch.py`                   | Cron-like batch scheduling. |

## Data Scale

Với config mặc định (`scripts/ingest_historical.py`):

- **Lookback**: 3650 ngày (~10 năm daily bars)
- **Symbols**: 60+ US stocks + indexes + crypto
- **Total rows**: ~60 × 2520 = ~150,000 OHLCV rows cho mỗi ingestion run
- **Storage**: Bronze (raw) + Silver (cleaned) + Gold (features) ≈ vài trăm MB Parquet local hoặc vài GB trên MinIO

## Scripts CLI (mỗi cái là implementation thật)

| Script                                     | Công nghệ | Vai trò |
|--------------------------------------------|-----------|---------|
| `scripts/ingest_historical.py`             | yfinance/Finnhub/AlphaVantage | REAL 10-năm OHLCV cho 60+ symbols, Bronze→Silver→Gold |
| `scripts/bootstrap_infrastructure.py`      | MinIO + Kafka admin           | Tạo buckets + topics |
| `scripts/init_iceberg_tables.py`           | pyiceberg                     | Tạo Bronze/Silver/Gold Iceberg tables |
| `scripts/run_spark_pipeline.py`            | PySpark                       | Spark implementation của Silver transform |
| `scripts/run_stream_publisher.py`          | websocket-client + kafka-python | WS → Kafka |
| `scripts/run_stream_consumer.py`           | kafka-python                  | Kafka → Bronze/Silver/Gold |
| `scripts/train_models.py`                  | sklearn/statsmodels/torch     | Train LR/ARIMA/LSTM |
| `scripts/run_backtest.py`                  | BacktestEngine                | Single backtest |
| `scripts/run_walk_forward.py`              | WalkForwardValidator          | Walk-forward validation |
| `scripts/run_indicators.py`                | IndicatorService              | Compute indicators ad-hoc |
| `scripts/run_macro_features.py`            | MacroFeatureBuilder           | Compute macro + regime features |
| `scripts/run_agent.py`                     | StockAnalysisAgent            | Headless AI agent |
| `scripts/transform_to_silver.py`           | Silver transform              | Legacy batch transform |