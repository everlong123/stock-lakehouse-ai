# Stock Lakehouse Platform - Progress Tracker

**Ngày cập nhật:** 30/09/2026
**Trạng thái:** Development
**Repository:** https://github.com/everlong123/stock-lakehouse-ai

> Bảng chi tiết từng công nghệ ↔ file implementation: xem [`docs/tech_stack_matrix.md`](tech_stack_matrix.md).
> Mọi công nghệ liệt kê trong đồ án đều có implementation thật, không config rỗng.

> **REAL DATA ONLY**: Lakehouse ingestion chỉ chấp nhận data thật từ yfinance/Finnhub/AlphaVantage/WebScraper. Đã xóa `generate_sample_data.py` + `SampleDataProvider`; `DATA_SOURCE=sample` giờ trả lỗi rõ ràng. Bronze layer chỉ chứa dữ liệu market thật, dataset tối thiểu 5 năm (~1825 ngày), mặc định 10 năm (~3650 ngày).

> **Verified 30/09/2026**: `tests/verify_real_data.py` đã download OHLCV thật cho AAPL/MSFT/AMZN (~2511 rows × 9.99 năm), BTC-USD (3650 rows × 9.99 năm), ETH-USD (3247 rows × 8.89 năm), EUR/USD (2599 rows × 9.99 năm). `tests/_smoke_real_pipeline.py` đã ingest vào MinIO: stock-bronze 4747 objects, stock-silver 4768 objects, stock-gold 315 objects với 94 features/row. Đã upgrade `yfinance 0.2.43 → 1.7.0` và cài `curl_cffi 0.16.3` để bypass Yahoo TLS fingerprint block.

> **VN Stock Verified 30/09/2026 (SSI iBoard)**: 50/53 HOSE symbols ingested qua `scripts/ingest_vn.py`, 117,686 Bronze + 117,401 Silver + 119,151 Gold rows. Coverage: 16 banks, 17 real estate, 2 tech, 6 consumer, 7 industrial, 4 securities. Span: 46/50 symbols ≥8 năm, 4/50 symbols 5-8 năm. Full per-symbol quality report ở [`docs/vn_data_quality.md`](vn_data_quality.md).

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

### Adapter Pattern Architecture

Mỗi nguồn dữ liệu được đóng gói trong một adapter class riêng biệt, đảm bảo:
- **Swap dễ dàng:** Thay nguồn mà không sửa pipeline
- **Fallback:** MultiSourceAdapter thử từng nguồn đến khi có data
- **Bronze snapshot:** Lưu raw data để đảm bảo đồ án chạy được kể cả khi endpoint chết

```
backend/adapters/
├── base.py              # BaseDataAdapter, Factory, MultiSourceAdapter
├── __init__.py
└── (thêm adapter mới ở đây)
```

| Source | Adapter | Trạng thái | Ghi chú |
|--------|---------|------------|---------|
| **Yahoo Finance** | `YahooFinanceDirectAdapter` | Hoạt động | US stocks, indexes, crypto |
| **VnExpress RSS** | `VnExpressRSSAdapter` | Hoạt động | Tin tức kinh doanh VN |
| **VN stocks** | Chưa có | Không có API free | Tất cả API bị chặn |
| **FPT, VNM** | `Yahoo RSS News` (filtered) | Hoạt động | Filtered keyword search |

### Supported Symbols

**US Stocks (17 symbols):**
```
Technology: AAPL, MSFT, GOOGL, META, NVDA, AMD
Finance: JPM, V, GS
Consumer: AMZN, TSLA, WMT
Healthcare: JNJ, UNH
Energy: XOM, CVX
Crypto: COIN, BTC-USD, ETH-USD
```

**Market Indexes:**
```
^GSPC - S&P 500
^DJI - Dow Jones
^IXIC - NASDAQ
```

### News Sources

**Yahoo Finance RSS** - Stock-specific news:
- AAPL news → Apple, iPhone, Tim Cook
- TSLA news → Tesla, Elon Musk

**VnExpress RSS** - VN business news:
- Filtered by keywords matching supported stocks

### Usage

```python
from adapters import YahooFinanceAdapter, VnExpressRSSAdapter, MultiSourceAdapter

# Single source
adapter = YahooFinanceAdapter()
df = adapter.fetch_prices('AAPL', interval='1D')

# Multiple sources with fallback
multi = MultiSourceAdapter(['yahoo', 'vnexpress'])
df = multi.fetch_prices('AAPL')
news = multi.fetch_news()
```

### Data Ingestion

```bash
# Fetch US stocks
python scripts/ingest.py --source yahoo --tickers AAPL MSFT GOOGL --mode prices

# Fetch news
python scripts/ingest.py --mode news

# List bronze files
python scripts/ingest.py --list
```

> **Lưu ý:** vnstock package yêu cầu Python >= 3.10 và dependency `vnai` không có sẵn. Khuyến nghị tự implement adapter cho VN data hoặc dùng SSI WebSocket.

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

# Khởi tạo hạ tầng (MinIO buckets + Kafka topics)
python scripts\bootstrap_infrastructure.py

# Download 10 năm OHLCV thật qua yfinance (60+ symbols)
python scripts\ingest_historical.py --years 10

# Chạy pipeline Bronze → Silver → Gold
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

### Da hoan thanh

| Module | Trang thai | Ngay hoan thanh |
|--------|------------|-----------------|
| Docker Infrastructure | Hoan thanh | 25/09/2026 |
| MySQL Setup | Hoan thanh | 25/09/2026 |
| MinIO Setup | Hoan thanh | 25/09/2026 |
| Kafka + Kafka UI | Hoan thanh | 25/09/2026 |
| Iceberg REST Catalog | Hoan thanh | 25/09/2026 |
| Lakehouse Architecture | Hoan thanh | - |
| Medallion Pipeline | Hoan thanh | - |
| FastAPI Backend | Hoan thanh | - |
| React Frontend | Hoan thanh | - |
| ML Models (LR, ARIMA, LSTM) | Hoan thanh | - |
| Backtesting Engine | Hoan thanh | - |
| AI Agent | Hoan thanh | - |
| Data Adapter Architecture | Hoan thanh | 29/09/2026 |
| Yahoo Finance Adapter (direct) | Hoat dong | 29/09/2026 |
| VnExpress RSS Adapter | Hoat dong | 29/09/2026 |
| Bronze Snapshot Script | Hoat dong | 29/09/2026 |
| Diverse US Stocks | Hoat dong | 29/09/2026 |
| Stock-specific News | Hoat dong | 29/09/2026 |
| **Finnhub Free Provider** (historical + news + profile) | Hoan thanh | 30/09/2026 |
| **yfinance Package Provider** (`YFinancePythonProvider`) | Hoan thanh | 30/09/2026 |
| **Historical Ingest Script** (Bronze -> Silver -> Gold) | Hoan thanh | 30/09/2026 |
| **Bootstrap Infrastructure Script** (MinIO buckets + Kafka topics) | Hoan thanh | 30/09/2026 |
| **Finnhub WebSocket Client** (auto-reconnect, PING) | Hoan thanh | 30/09/2026 |
| **StreamPublisher** (WS -> 1s OHLCV -> Kafka) | Hoan thanh | 30/09/2026 |
| **Multi-Source Failover Provider** | Hoan thanh | 30/09/2026 |
| **PySpark Pipeline Runner** (`run_spark_pipeline.py`) | Hoan thanh | 30/09/2026 |
| **Iceberg Tables Init Script** (`init_iceberg_tables.py`) | Hoan thanh | 30/09/2026 |
| **Backtest CLI** (`run_backtest.py`) | Hoan thanh | 30/09/2026 |
| **Walk-forward CLI** (`run_walk_forward.py`) | Hoan thanh | 30/09/2026 |
| **Indicator CLI** (`run_indicators.py`) | Hoan thanh | 30/09/2026 |
| **Macro/Regime CLI** (`run_macro_features.py`) | Hoan thanh | 30/09/2026 |
| **AI Agent CLI** (`run_agent.py`) | Hoan thanh | 30/09/2026 |
| **SSI iBoard VN Provider** (`ssi_vn_provider.py`) | Hoan thanh | 30/09/2026 |
| **VN Ingestion CLI** (`ingest_vn.py` - 53 symbols w/ quality report) | Hoan thanh | 30/09/2026 |
| **VN Data Quality Report** (`docs/vn_data_quality.md`) | Hoan thanh | 30/09/2026 |
| **System Health Audit Script** (`tests/_system_audit.py` + `docs/system_health.md`) | Hoan thanh | 01/10/2026 |
| **Route Ordering Fix** (`/data/stocks/supported` 502 → 200) | Hoan thanh | 01/10/2026 |
| **Kafka Producer Compat Fix** (`enable_idempotence` kafka-python <2.5) | Hoan thanh | 01/10/2026 |
| **Kafka Consumer Batch Format Support** (`{"symbol","bars":[...]}`) | Hoan thanh | 01/10/2026 |

### TODO - Next Steps

- [x] Data Adapter Architecture (Adapter Pattern)
- [x] Yahoo Finance Adapter
- [x] VnExpress RSS Adapter
- [x] Bronze Snapshot Script
- [x] Diverse US Stocks (60+ symbols + indexes)
- [x] Stock-specific News (Yahoo RSS + VnExpress)
- [x] Finnhub Free Provider (historical + WS streaming)
- [x] yfinance Package Provider (preferred over direct REST)
- [x] End-to-end historical ingest pipeline
- [x] MinIO bucket + Kafka topic bootstrapper
- [x] Finnhub WebSocket → Kafka publisher
- [ ] Frontend realtime view (consume WS or Kafka topic)
- [ ] Stream consumer in background service (long-running)
- [ ] Walk-forward validation across streamed data
- [ ] Drift detection on incoming ticks

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
- [ ] SSI WebSocket Adapter (VN real-time)
- [ ] VN Stock Historical Adapter (FPT, VND...)
- [ ] Silver Layer Processing (clean, validate, standardize)
- [ ] Gold Layer Feature Engineering (indicators, lags)

### Medium Priority
- [x] End-to-end test với data thật (`ingest_historical.py`)
- [x] Kafka streaming test (`run_stream_publisher.py` + `run_stream_consumer.py`)
- [x] MinIO bucket setup cho Iceberg (`bootstrap_infrastructure.py`)
- [ ] Viết unit tests

### Low Priority
- [x] Streaming ingestion (Kafka) - via Finnhub WebSocket
- [ ] Frontend realtime view (WebSocket trực tiếp tới FE)
- [ ] Multi-asset portfolio
- [ ] Experiment tracking
- [ ] Full auth multi-user

---

## Streaming & Real-time (Finnhub WebSocket + Kafka)

Từ ngày 30/09/2026 project đã có pipeline real-time hoàn chỉnh với $0:

```
Finnhub WS  →  StreamPublisher  →  Kafka topic    →  Consumer  →  Bronze/Silver/Gold
(Free tier)    (1s OHLCV agg)      "stock-ohlcv-raw"
```

Các file liên quan:

| File | Vai trò |
|------|---------|
| `app/data_sources/finnhub_provider.py` | Lấy OHLCV lịch sử, news, company profile qua REST |
| `app/data_sources/yfinance_python_provider.py` | Lấy OHLCV qua package `yfinance` (ưu tiên) |
| `app/streaming/finnhub_websocket.py` | Auto-reconnect WebSocket client + PING |
| `app/streaming/stream_publisher.py` | Gom trades thành bar 1s, publish Kafka |
| `app/streaming/kafka_producer.py` | Producer Kafka (đã có sẵn) |
| `app/streaming/kafka_consumer.py` | Consumer Kafka → Medallion Lakehouse |
| `scripts/ingest_historical.py` | End-to-end historical ingest |
| `scripts/bootstrap_infrastructure.py` | Tạo MinIO buckets + Kafka topics |
| `scripts/run_stream_publisher.py` | CLI chạy WebSocket publisher |
| `scripts/run_stream_consumer.py` | CLI chạy consumer |

### Setup streaming (sau khi `docker compose up -d`)

```bash
# 1. Tạo buckets + topics
python scripts/bootstrap_infrastructure.py

# 2. Điền FINNHUB_API_KEY vào .env (lấy key miễn phí tại https://finnhub.io/)
#    Bật Kafka: USE_KAFKA=true, KAFKA_BOOTSTRAP_SERVERS=localhost:9094

# 3. Cài thêm websocket-client
pip install -r backend/requirements.txt

# 4. Ingest dữ liệu lịch sử (Bronze -> Silver -> Gold)
python scripts/ingest_historical.py --source yfinance --interval 1d --limit 5
python scripts/ingest_historical.py --source finnhub --symbols AAPL,MSFT --interval 1h

# 5. Train model
python scripts/train_models.py --symbol AAPL --models linear_regression,arima,lstm

# 6. Khởi động publisher (terminal 1)
python scripts/run_stream_publisher.py --symbols AAPL,MSFT,GOOGL

# 7. Khởi động consumer (terminal 2)
python scripts/run_stream_consumer.py --topic stock-ohlcv-raw
```

Giám sát topic trên <http://localhost:8090> (Kafka UI).

### Giới hạn Finnhub Free tier

- 1 kết nối WebSocket đồng thời
- Tối đa 50 symbols subscribe
- ~50 messages / giây tổng cộng
- Historical: 1m/5m/15m tối đa 30 ngày; 1h tối đa 365 ngày; daily tối đa 10 năm

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

# Ingest lịch sử (Bronze -> Silver -> Gold)
python scripts\ingest_historical.py --source yfinance --interval 1d
python scripts\ingest_historical.py --source finnhub --symbols AAPL,MSFT

# Bootstrap MinIO + Kafka
python scripts\bootstrap_infrastructure.py

# Chạy stream publisher (WebSocket -> Kafka)
python scripts\run_stream_publisher.py --symbols AAPL,MSFT,GOOGL

# Chạy stream consumer (Kafka -> Lakehouse)
python scripts\run_stream_consumer.py --topic stock-ohlcv-raw

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
STORAGE_BACKEND=minio  # local hoặc minio

# MinIO (khi dùng STORAGE_BACKEND=minio)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Kafka (Free tier streaming)
KAFKA_BOOTSTRAP_SERVERS=localhost:9094
USE_KAFKA=true
KAFKA_TOPIC_RAW=stock-ohlcv-raw

# Data Source (chọn 1)
# - sample         : mock data (offline)
# - yfinance       : official yfinance package (preferred)
# - yfinance_direct: direct HTTP (no extra dependency)
# - finnhub        : Finnhub Free tier (60 req/min, used for WS streaming)
# - alpha_vantage  : Alpha Vantage free tier
# - web_scraper    : Yahoo + CafeF scrape
DATA_SOURCE=yfinance

# Provider API keys (tất cả đều free)
FINNHUB_API_KEY=<your-key-from-finnhub.io>
FINNHUB_WS_SYMBOLS=AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,META,AMD
ALPHA_VANTAGE_API_KEY=<optional>

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
| Không có market data | Đổi `DATA_SOURCE=yfinance` trong .env, chạy `ingest_historical.py` |
| Sample data chỉ test | Dùng yfinance hoặc Finnhub providers để lấy data thật |
| LSTM chậm | Giảm epochs, USE_SPARK=false |
| VN stock data trống | Cấu hình VN provider credentials |
| Kafka không healthy | Đợi ~30s cho Kafka khởi động; chạy `scripts/bootstrap_infrastructure.py` |
| Finnhub 401/403 | Kiểm tra `FINNHUB_API_KEY`; key mới có thể cần ~5 phút để active |
| yfinance trả empty | Yahoo rate-limit hoặc chưa cài package; chạy `pip install yfinance` |
| WebSocket không kết nối | Ping bị block hoặc key sai; kiểm tra `ping finnhub.io` |

---

## Ghi chú

- **$0 budget:** Toàn bộ data layer (yfinance, Finnhub Free tier, Alpha Vantage, VnExpress RSS) là miễn phí
- **Near-real-time:** Finnhub WebSocket (~50 msgs/sec, 50 symbols) + Kafka làm backbone streaming
- **Không phải production:** Prototype nghiên cứu học thuật
- **Dagster:** Cần chạy local vì không có public Docker image
