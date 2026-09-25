# Stock Lakehouse Platform - Progress Tracker

**Ngày cập nhật:** 25/09/2026  
**Trạng thái:** Development  
**Repository:** https://github.com/everlong123/stock-lakehouse-ai

---

## Mục lục

1. [Tổng quan](#tổng-quan)
2. [Kiến trúc](#kiến-trúc)
3. [Setup - Hướng dẫn chạy](#setup---hướng-dẫn-chạy)
4. [Tiến độ thực hiện](#tiến-độ-thực-hiện)
5. [Đã hoàn thành](#đã-hoàn-thành)
6. [TODO](#todo)
7. [Các lệnh thường dùng](#các-lệnh-thường-dùng)
8. [Truy cập dịch vụ](#truy-cập-dịch-vụ)

---

## Tổng quan

**Project:** Xây dựng nền tảng Data Lakehouse phân tích và dự báo chứng khoán thời gian thực ứng dụng học sâu và AI Agent.

**Đây là prototype nghiên cứu học thuật:**
- Không giao dịch chứng khoán thật
- Không tự động đặt lệnh mua/bán
- Không cam kết lợi nhuận
- Backtesting chỉ đánh giá hiệu suất lịch sử giả định

---

## Cấu trúc Project

```
stock-lakehouse-ai/
├── backend/              # FastAPI backend
│   ├── app/             # API routes, models
│   ├── scripts/         # Data generation, pipelines
│   └── requirements.txt
├── frontend/            # React + Vite frontend
├── dagster/             # Dagster orchestration
├── docs/                # Documentation
├── docker-compose.yml   # Docker infrastructure
├── .env                 # Environment variables
└── README.md
```

## Data Sources

| Source | Mô tả | Trạng thái |
|--------|--------|------------|
| **Sample Data** | Mock data để test nhanh | ✅ Sẵn sàng |
| **yfinance** | Yahoo Finance API (quốc tế) | ✅ Có sẵn |
| **VN Stock Providers** | cafef, SSI, VCBS (Việt Nam) | 🔜 Cần cấu hình |

> **Lưu ý:** `generate_sample_data.py` chỉ dùng để **test hệ thống**. Data thật sẽ lấy từ yfinance hoặc các provider Việt Nam.

---

## Kiến trúc

```
Stock Data Source (sample | yfinance polling)
        ↓
Data Ingestion
        ↓
Bronze Layer (Parquet/Iceberg)
        ↓
Apache Spark / Pandas
        ↓
Silver Layer (cleaned OHLCV + quality report)
        ↓
Feature Engineering
        ↓
Gold Layer (indicators, lags, targets)
        ↓
Technical Analysis | Forecasting | Backtesting
        ↓
FastAPI
        ↓
React Web App          AI Agent (tool calling)
```

### Medallion Architecture

| Layer | Mô tả |
|-------|-------|
| **Bronze** | Dữ liệu gần nguồn, append, lineage, duplicate check |
| **Silver** | Chuẩn hóa timezone UTC, ép kiểu, kiểm tra OHLC/volume |
| **Gold** | Đặc trưng và target (shift -1, không rò rỉ tương lai) |

### Technologies

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic |
| Database | MySQL 8, SQLite (Iceberg catalog) |
| Storage | MinIO (S3-compatible), Apache Parquet, Apache Iceberg |
| Orchestration | Dagster (manual fallback) |
| Streaming | Apache Kafka |
| ML | scikit-learn, statsmodels, PyTorch |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS |

---

## Setup - Hướng dẫn chạy

### Bước 1: Docker Infrastructure

```bash
cd stock-lakehouse-platform

# Build và chạy tất cả services
docker compose up -d

# Kiểm tra trạng thái
docker compose ps
```

**Services đang chạy:**
| Service | Port | URL |
|---------|------|-----|
| MySQL | 3307 | localhost:3307 |
| MinIO API | 9000 | localhost:9000 |
| MinIO Console | 9001 | localhost:9001 |
| Adminer | 8081 | localhost:8081 |
| Kafka | 9092, 9094 | localhost:9094 |
| Kafka UI | 8090 | localhost:8090 |
| Iceberg REST | 8181 | localhost:8181 |

### Bước 2: Backend

```bash
cd backend

# Tạo virtual environment (Python 3.11)
py -3.11 -m venv .venv
.venv\Scripts\activate

# Cài đặt dependencies
pip install -r requirements.txt

# Copy và chỉnh sửa .env
copy ..\.env.example ..\.env
copy ..\.env.example .env

# Khởi tạo database
python scripts\init_database.py

# Sinh sample data
python scripts\generate_sample_data.py

# Chạy pipeline
python scripts\run_pipeline.py --symbol ALL

# Start server
uvicorn app.main:app --reload
```

### Bước 3: Frontend

```bash
cd frontend

# Cài đặt dependencies
npm install

# Copy .env
copy .env.example .env

# Start dev server
npm run dev
```

### Bước 4: Truy cập

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| MinIO Console | http://localhost:9001 |

---

## Tiến độ thực hiện

### ✅ Đã hoàn thành

| Module | Trạng thái | Ngày hoàn thành |
|--------|------------|-----------------|
| Docker Infrastructure | ✅ Hoàn thành | 25/09/2026 |
| MySQL Setup | ✅ Hoàn thành | 25/09/2026 |
| MinIO Setup | ✅ Hoàn thành | 25/09/2026 |
| Kafka + Kafka UI | ✅ Hoàn thành | 25/09/2026 |
| Iceberg REST Catalog | ✅ Hoàn thành | 25/09/2026 |
| Lakehouse Architecture | ✅ Hoàn thành | - |
| Medallion Pipeline | ✅ Hoàn thành | - |
| FastAPI Backend | ✅ Hoàn thành | - |
| React Frontend | ✅ Hoàn thành | - |
| ML Models (LR, ARIMA, LSTM) | ✅ Hoàn thành | - |
| Backtesting Engine | ✅ Hoàn thành | - |
| AI Agent | ✅ Hoàn thành | - |

### 🔄 Đang phát triển

| Module | Trạng thái | Ghi chú |
|--------|------------|---------|
| Dagster Orchestration | ⚠️ Cần local setup | Không có public Docker image |

### 📋 TODO - Next Steps

- [ ] Cấu hình data source (yfinance hoặc VN providers)
- [ ] Tạo bucket trên MinIO cho Iceberg
- [ ] Test Kafka producer/consumer
- [ ] Chạy end-to-end pipeline với data thật
- [ ] Setup Dagster local
- [ ] Viết unit tests

---

## Đã hoàn thành

### Docker Setup (25/09/2026)
- Thay `bitnami/kafka` bằng `apache/kafka:3.8.0` (bitnami không có public image)
- Đổi Kafka UI port 8080 → 8090 (tránh conflict)
- Xóa Dagster services (không có public image)
- Dọn dẹp unused volumes và build cache

**Space sau khi dọn:**
- Images: 3.6 GB
- Volumes: 219 MB
- Build Cache: 0 B

### Database Schema
- `users` - Tài khoản người dùng (bcrypt password)
- `pipeline_runs` - Lịch sử chạy pipeline
- `model_runs` - Lịch sử huấn luyện model
- `backtest_runs` - Lịch sử backtest
- `agent_conversations` - Lịch sử AI Agent

### Features

**Dashboard:**
- Giá, % thay đổi, volume
- RSI, prediction
- Nến, volume chart
- Pipeline status

**Market Data:**
- Nến chart
- Bảng OHLCV
- CSV export

**Technical Analysis:**
- SMA, EMA, RSI, MACD, Bollinger Bands
- Bật/tắt indicator

**Forecasting:**
- Linear Regression
- ARIMA
- LSTM (PyTorch, CPU)
- Actual vs Predicted chart
- Model comparison

**Backtesting:**
- MA Crossover Strategy
- RSI Strategy
- Equity curve, drawdown
- Trade history
- Metrics: Total Return, Win Rate, Sharpe Ratio, Max Drawdown, Profit Factor

**AI Agent:**
- Tool calling vào backend
- Local tool router (fallback khi không có OpenAI key)
- Lịch sử chat lưu MySQL

---

## TODO

### High Priority
- [ ] Cấu hình data source thật (yfinance/VN providers)
- [ ] End-to-end test pipeline với data thật
- [ ] MinIO bucket setup cho Iceberg

### Medium Priority
- [ ] Kafka streaming test
- [ ] Setup Dagster local
- [ ] Viết unit tests
- [ ] Performance optimization cho LSTM

### Low Priority
- [ ] Streaming ingestion
- [ ] Multi-asset portfolio
- [ ] Experiment tracking
- [ ] Full auth multi-user

---

## Các lệnh thường dùng

### Docker
```bash
# Xem trạng thái
docker compose ps

# Xem logs
docker compose logs -f kafka

# Restart service
docker compose restart kafka

# Dừng tất cả
docker compose down

# Xóa data (cẩn thận!)
docker compose down -v
```

### Backend
```bash
cd backend
.venv\Scripts\activate

# Chạy pipeline
python scripts\run_pipeline.py --symbol AAPL
python scripts\run_pipeline.py --symbol ALL

# Train models
python scripts\train_models.py --symbol AAPL --models linear_regression,arima,lstm

# Tests
pytest

# API Server
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm run dev
```

---

## Truy cập dịch vụ

### MySQL
```bash
# Qua Adminer
http://localhost:8081
# System: MySQL
# Server: mysql
# Username: root
# Password: 123456
# Database: stock_lakehouse

# Qua command line
mysql -h 127.0.0.1 -P 3307 -u root -p123456
```

### MinIO
```bash
# Console
http://localhost:9001
# Access Key: minioadmin
# Secret Key: minioadmin

# Credentials
minioadmin / minioadmin
```

### Kafka
```bash
# Kafka UI
http://localhost:8090

# Port: localhost:9094
```

### Iceberg
```bash
# REST API
http://localhost:8181
```

---

## Cấu hình .env

```bash
# Database
MYSQL_HOST=localhost
MYSQL_PORT=3307
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=stock_lakehouse

# Storage
STORAGE_BACKEND=local  # hoặc minio

# MinIO (khi dùng STORAGE_BACKEND=minio)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9094
USE_KAFKA=false

# Iceberg
USE_ICEBERG=false
ICEBERG_CATALOG_URI=http://localhost:8181

# Data Source
# - sample: Mock data (chỉ để test nhanh)
# - yfinance: Yahoo Finance API (data quốc tế: AAPL, MSFT...)
# - vnstock/vninvest: Vietnamese stock providers
DATA_SOURCE=sample

# AI Agent (optional)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Spark
USE_SPARK=false
```

---

## Troubleshooting

| Vấn đề | Cách xử lý |
|--------|-------------|
| MySQL disconnected | Kiểm tra Docker container đang chạy |
| Không có market data | Đổi `DATA_SOURCE=yfinance` trong .env, chạy `run_pipeline.py` |
| Sample data chỉ test | Dùng yfinance hoặc VN providers để lấy data thật |
| LSTM chậm | Giảm epochs, USE_SPARK=false |
| VN stock data trống | Cấu hình VN provider credentials |
| Kafka không healthy | Đợi ~30s cho Kafka khởi động |

---

## Ghi chú

- **Near-real-time:** yfinance polling, không phải tick-level
- **Không phải production:** Prototype nghiên cứu học thuật
- **Dagster:** Cần chạy local vì không có public Docker image
