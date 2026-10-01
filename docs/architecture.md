# Kiến trúc hệ thống

Nền tảng là một prototype khóa luận, không phải hệ thống giao dịch thật.

```
Real Data Sources (yfinance | Finnhub | Alpha Vantage | SSI iBoard)
        |
        v
Data Ingestion (adapter factory + multi-source failover)
        |
        v
Bronze Layer (Parquet, partition symbol/year/month, append-only)
        |
        v
Silver Layer (cleaned OHLCV + quality report + _errors/)
        |
        v
Gold Layer (94 features: technical + advanced + macro + composite + target)
        |
        +-- Technical Analysis (SMA/EMA/RSI/MACD/Bollinger/ATR/ADX)
        +-- Forecasting (Linear Regression / ARIMA / LSTM)
        +-- Backtesting (MA Crossover / RSI Strategy)
        +-- AI Agent (Gemini Free + local tool router) --> Frontend
        |
        v
FastAPI (REST + Swagger)
        |
        v
React + Vite Frontend
```

## Medallion

- **Bronze**: dữ liệu gần nguồn, append, lineage (`_lineage.json`), duplicate check theo `(symbol, timestamp)`.
- **Silver**: chuẩn hóa timezone UTC, ép kiểu, kiểm OHLC/volume. Bản ghi lỗi được đếm và ghi `silver/_errors/`, không silent drop.
- **Gold**: đặc trưng và target. Target được `shift(-1)` nên không rò rỉ tương lai vào feature.

## Lưu trữ

- `STORAGE_BACKEND=local`: thư mục `backend/data/`.
- `STORAGE_BACKEND=minio`: bucket `stock-bronze`, `stock-silver`, `stock-gold`, `stock-models`, `stock-backtests`.
- Nếu MinIO không chạy, hệ thống tự fallback về `LocalStorageBackend` (không crash).

## Engine transform

- Engine chính là **Pandas** (in-process, không cần service riêng). Dữ liệu hiện tại ~120.000 rows Gold, Pandas xử lý thoải mái.
- Iceberg REST Catalog chạy trong Docker để quản lý schema (time-travel, schema evolution), không dùng Spark.

## MySQL

MySQL 8 chỉ lưu metadata: `users`, `pipeline_runs`, `model_runs`, `backtest_runs`, `agent_conversations`. Schema được quản lý bằng Alembic.

OHLCV lịch sử thuộc Lakehouse (Parquet trên MinIO), không nhồi vào MySQL.

## Near-real-time

yfinance không cung cấp tick-level. Project lấy dữ liệu theo polling interval và gọi đó là near-real-time. Finnhub WebSocket (Free tier) cung cấp trade ticks, được gom thành bar 1s qua `StreamPublisher` rồi publish lên Kafka topic `stock-ohlcv-raw`.

## Synthetic fallback cho UI demo

Khi Lakehouse trống (chưa ingest symbol nào), `MarketService._synthetic_history()` sinh deterministic OHLCV (252 bars) theo ticker để chart demo không bị trống. Dữ liệu này **không** ghi vào Bronze/Silver/Gold - chỉ là view layer cho UI.

## Ràng buộc học thuật

- Không khẳng định LSTM luôn tốt nhất. Model tốt hơn phải dựa trên MAE/RMSE/MAPE/Directional Accuracy thực tế.
- Backtesting chỉ đánh giá hiệu suất lịch sử giả định, không chứng minh lợi nhuận tương lai.
- AI Agent có system prompt rõ ràng: "kết quả phân tích và dự báo không phải khuyến nghị đầu tư".
