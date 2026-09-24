# Kiến trúc hệ thống

Nền tảng là một prototype khóa luận, không phải hệ thống giao dịch thật.

```
Stock Data Source (sample | yfinance polling)
        ↓
Data Ingestion
        ↓
Bronze Layer (Parquet, partition symbol/year/month)
        ↓
Apache Spark / Pandas (USE_SPARK)
        ↓
Silver Layer (cleaned OHLCV + quality report)
        ↓
Feature Engineering
        ↓
Gold Layer (indicators, lags, targets)
        ↓
Technical Analysis | Forecasting | Backtesting | Analytics
        ↓
FastAPI
        ↓
React Web App          AI Agent (tool calling)
```

## Medallion

- **Bronze**: dữ liệu gần nguồn, append, lineage, duplicate check.
- **Silver**: chuẩn hóa timezone UTC, ép kiểu, kiểm OHLC/volume. Record lỗi được đếm và ghi `_errors`, không silent drop.
- **Gold**: đặc trưng và target. Target được `shift(-1)` nên không rò rỉ tương lai vào feature.

## Lưu trữ

- `STORAGE_BACKEND=local`: thư mục `backend/data`.
- `STORAGE_BACKEND=minio`: bucket `stock-bronze`, `stock-silver`, `stock-gold`, `stock-models`, `stock-backtests`.
- Nếu MinIO không chạy, hệ thống tự fallback local.

## Spark

- `USE_SPARK=false` (mặc định): Pandas.
- `USE_SPARK=true`: PySpark cho Bronze→Silver và Silver→Gold. Output schema tương thích.

## MySQL

MySQL 8 chỉ lưu metadata: users, pipeline_runs, model_runs, backtest_runs, agent_conversations.

OHLCV lịch sử thuộc Lakehouse (Parquet), không nhồi vào MySQL.

## Near-real-time

yfinance không cung cấp tick-level. Prototype lấy dữ liệu theo polling interval và gọi đó là near-real-time.

## Ràng buộc học thuật

Không khẳng định LSTM luôn tốt nhất. Model tốt hơn phải dựa trên MAE/RMSE/MAPE/Directional Accuracy thực tế.

Backtesting chỉ đánh giá hiệu suất lịch sử giả định, không chứng minh lợi nhuận tương lai.
