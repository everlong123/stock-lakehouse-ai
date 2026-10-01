# Stock Lakehouse Platform - Progress Tracker

**Ngày cập nhật:** 01/10/2026
**Trạng thái:** Prototype hoàn chỉnh cho báo cáo KLTN
**Repository:** https://github.com/everlong123/stock-lakehouse-ai

> Bảng chi tiết từng công nghệ ↔ file implementation: xem [`docs/tech_stack_matrix.md`](tech_stack_matrix.md).
> Mọi công nghệ liệt kê trong đồ án đều có implementation thật, không config rỗng.

> **REAL DATA ONLY**: Lakehouse ingestion chỉ chấp nhận data thật từ yfinance / Finnhub / AlphaVantage / SSI iBoard. Bronze layer chỉ chứa dữ liệu market thật, dataset tối thiểu 5 năm (~1825 ngày), mặc định 10 năm (~3650 ngày).

> **Verified 30/09/2026**: `tests/verify_real_data.py` đã download OHLCV thật cho AAPL/MSFT/AMZN (~2511 rows × 9.99 năm), BTC-USD (3650 rows × 9.99 năm), ETH-USD (3247 rows × 8.89 năm), EUR/USD (2599 rows × 9.99 năm). `tests/_smoke_real_pipeline.py` đã ingest vào MinIO: stock-bronze 4747 objects, stock-silver 4768 objects, stock-gold 315 objects với 94 features/row. Đã upgrade `yfinance 0.2.43 → 1.7.0` và cài `curl_cffi 0.16.3` để bypass Yahoo TLS fingerprint block.

> **VN Stock Verified 30/09/2026 (SSI iBoard)**: 50/53 HOSE symbols ingested qua `scripts/ingest_vn.py`, 117,686 Bronze + 117,401 Silver + 119,151 Gold rows. Coverage: 16 banks, 17 real estate, 2 tech, 6 consumer, 7 industrial, 4 securities. Span: 46/50 symbols ≥8 năm, 4/50 symbols 5-8 năm. Full per-symbol quality report ở [`docs/vn_data_quality.md`](vn_data_quality.md).

> **Verified 01/10/2026**: Toàn bộ web UI (React) đã test end-to-end với backend FastAPI. Tất cả page (Dashboard, Market Data, Technical Analysis, Forecasting, Backtesting, AI Agent, System Status) render đúng và gọi API thật. AI Agent route 5/5 câu hỏi phức tạp qua Gemini Free API đến đúng tool (`get_market_summary`, `query_stock_data`, `calculate_indicators`, `run_backtest`). Vite proxy `/api/v1` → `127.0.0.1:8000` đã cấu hình xong, sửa lỗi 404 trước đó. Synthetic fallback trong `MarketService` đảm bảo chart demo luôn có data khi Lakehouse chưa populate.

---

## Mục lục

1. [Tổng quan](#tổng-quan)
2. [Setup - Hướng dẫn chạy](#setup---hướng-dẫn-chạy)
3. [Cấu trúc Project](#cấu-trúc-project)
4. [Data Sources](#data-sources)
5. [Kiến trúc](#kiến-trúc)
6. [Tiến độ thực hiện](#tiến-độ-thực-hiện)
7. [Đã hoàn thành](#đã-hoàn-thành)
8. [Streaming & Real-time](#streaming--real-time-kafka)
9. [Các lệnh thường dùng](#các-lệnh-thường-dùng)
10. [Cấu hình .env](#cấu-hình-env)
11. [Troubleshooting](#troubleshooting)

---

## Tổng quan

**Project:** Xây dựng nền tảng Data Lakehouse phân tích và dự báo chứng khoán ứng dụng học sâu và AI Agent.

**Đây là prototype nghiên cứu học thuật:**

- Không giao dịch chứng khoán thật.
- Không tự động đặt lệnh mua/bán.
- Không cam kết lợi nhuận.
- Backtesting chỉ đánh giá hiệu suất lịch sử giả định.

**Tech stack tóm tắt:**

- Backend: Python 3.11 + FastAPI + SQLAlchemy 2 + Alembic.
- Metadata DB: MySQL 8 (`stock_lakehouse`).
- Object Storage: MinIO (S3-compatible).
- Lakehouse format: Apache Parquet + Apache Iceberg (REST catalog ở `localhost:8181`).
- Streaming: Apache Kafka 3.8 (KRaft, không ZooKeeper).
- ML: scikit-learn, statsmodels (ARIMA), PyTorch (LSTM).
- AI Agent: Gemini Free API (`gemini-2.0-flash-exp`) + local tool router.
- Frontend: React 18 + Vite 5 + TypeScript + TailwindCSS + TanStack Query + Recharts.

---

## Setup - Hướng dẫn chạy

### Bước 1 - Khởi động Docker Infrastructure

Tại thư mục gốc `stock-lakehouse-ai/`:

```bash
docker compose up -d
docker compose ps
```

Đợi ~20-30 giây cho đến khi cả 4 container `healthy`/`running`:

| Service | Container | Port | URL |
|---------|-----------|------|-----|
| MySQL 8 | stock-lakehouse-mysql | 3307 | (không UI; dùng CLI hoặc MySQL client) |
| MinIO API | 9000 | localhost:9000 | - |
| MinIO Console | 9001 | localhost:9001 | http://localhost:9001 |
| Iceberg REST | 8181 | localhost:8181 | http://localhost:8181/v1/config |
| Kafka broker (external) | 9094 | localhost:9094 | - |
| Kafka broker (internal) | 9092 | (chỉ trong Docker network) | - |

Nếu container nào lâu healthy, xem log: `docker compose logs -f <service>`.

### Bước 2 - Backend

```powershell
cd backend

# 1) Tạo venv (Python 3.11)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) Cài dependencies
pip install -r requirements.txt

# 3) Tạo database + chạy Alembic migrations (idempotent)
python scripts\init_database.py

# 4) (optional) Tạo MinIO buckets + Kafka topics
python scripts\bootstrap_infrastructure.py

# 5) (optional) Ingest dữ liệu lịch sử thật (Bronze -> Silver -> Gold)
python scripts\ingest_historical.py --source multi_source --years 10
python scripts\ingest_vn.py --years 10

# 6) Chạy API server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Sau khi server chạy:

- Swagger UI: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/v1/health

### Bước 3 - Frontend

```powershell
cd frontend

# 1) Cài dependencies
npm install

# 2) Tạo .env (đã có sẵn .env.example, copy hoặc tạo mới)
# VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1

# 3) Start dev server
npm run dev
```

Frontend chạy tại: **http://127.0.0.1:5173**.

> Vite đã cấu hình proxy `/api/v1` -> `http://127.0.0.1:8000`. Khi gọi `/api/v1/...` từ browser, request được forward thẳng đến backend local.

### Bước 4 - Truy cập

| Service | URL |
|---------|-----|
| Frontend (web app) | http://127.0.0.1:5173 |
| Backend Swagger | http://127.0.0.1:8000/docs |
| Backend Health | http://127.0.0.1:8000/api/v1/health |
| MinIO Console | http://localhost:9001 |
| Iceberg REST | http://localhost:8181/v1/config |

---

## Cấu trúc Project

```
stock-lakehouse-ai/
├── backend/
│   ├── app/                        # FastAPI app
│   │   ├── agent/                  # AI Agent (Gemini + tool router)
│   │   ├── api/                    # REST routes
│   │   ├── backtesting/            # Engine, strategies, metrics
│   │   ├── core/                   # Config, logging
│   │   ├── data_sources/           # yfinance/Finnhub/AlphaVantage/SSI providers
│   │   ├── database/               # SQLAlchemy models + session
│   │   ├── features/               # Gold feature builders
│   │   ├── forecasting/            # LR / ARIMA / LSTM
│   │   ├── indicators/             # SMA/EMA/RSI/MACD/Bollinger
│   │   ├── lakehouse/              # Bronze/Silver/Gold + Iceberg manager
│   │   ├── services/               # MarketService, IndicatorService, ForecastService...
│   │   └── streaming/              # Kafka producer/consumer, Finnhub WS
│   ├── scripts/                    # CLI scripts (ingest, bootstrap, train, backtest...)
│   ├── alembic/                    # Database migrations
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── src/                        # React app
│   ├── .env                        # VITE_API_BASE_URL
│   └── package.json
├── docs/                           # Documentation
├── docker-compose.yml              # mysql + minio + iceberg-rest + kafka
├── .env                            # Backend env (MySQL/MinIO/Kafka/API keys)
└── README.md
```

---

## Data Sources

### Adapter Pattern Architecture

Mỗi nguồn dữ liệu được đóng gói trong một adapter class riêng biệt, đảm bảo:

- **Swap dễ dàng:** Thay nguồn mà không sửa pipeline.
- **Fallback:** `MultiSourceProvider` thử từng nguồn đến khi có data.
- **Bronze snapshot:** Lưu raw data để đảm bảo đồ án chạy được kể cả khi endpoint chết.

```
backend/app/data_sources/
├── base.py                          # BaseDataProvider + provider contracts
├── factory.py                       # ProviderFactory, MultiSourceProvider
├── yfinance_python_provider.py      # primary (no key, real OHLCV)
├── yfinance_provider.py             # legacy thin wrapper
├── finnhub_provider.py              # free tier + WS
├── alpha_vantage_provider.py        # free tier REST
├── ssi_vn_provider.py               # HOSE/HNX qua SSI iBoard
├── web_scraper_provider.py          # CafeF + VnExpress fallback
├── market_index_provider.py
├── macro_provider.py
├── fundamental_provider.py
├── enhanced_fundamental_provider.py
├── news_sentiment_provider.py
├── enhanced_news_sentiment_provider.py
├── orderbook_provider.py
└── multi_source.py                  # failover chain
```

| Source | Adapter | Trạng thái | Ghi chú |
|--------|---------|------------|---------|
| **Yahoo Finance** | `YFinancePythonProvider` | Hoạt động | US stocks, indexes, crypto |
| **Finnhub** | `FinnhubProvider` | Hoạt động | Free tier OHLCV + WS streaming |
| **Alpha Vantage** | `AlphaVantageProvider` | Hoạt động | Free tier daily OHLCV |
| **SSI iBoard** | `SSIVNProvider` | Hoạt động | Cổ phiếu VN (HOSE/HNX/UPCOM) |
| **Web scraper** | `WebScraperProvider` | Backup | CafeF (VN) + Yahoo HTTP fallback |

### Supported Symbols

**US Stocks (60+):**
```
Technology: AAPL, MSFT, GOOGL, META, NVDA, AMD, ORCL, CRM, ADBE
Finance: JPM, V, MA, GS, BAC, MS, BLK
Consumer: AMZN, TSLA, WMT, HD, NKE, MCD, SBUX
Healthcare: JNJ, UNH, PFE, MRK, ABBV, LLY
Energy: XOM, CVX, COP, SLB
Crypto: COIN, BTC-USD, ETH-USD, MSTR
```

**Vietnam (HOSE/HNX - 53 symbols):**
```
Banks: VCB, TCB, MBB, ACB, BID, CTG, HDB, STB, TPB, MSB, SHB, LPB, EIB, OCB, VIB, NVB
Real estate: VHM, VRE, KDH, VIC, NVL, PDR, BCM, HDG, DIG, FCN, ITA, HCM, NSC, MBC, SBT, IMP, PLD
Tech: FPT, CMG
Consumer / Retail: MWG, PNJ, MSN, SAB, VNM, PNVN
Industrial: HPG, GAS, PLX, POW, REE, KDC, DHG
Securities: SSI, VND, VCI, SHS
```

**Market Indexes:**
```
^GSPC - S&P 500
^DJI  - Dow Jones
^IXIC - NASDAQ
```

---

## Kiến trúc

```
Real Data Sources (yfinance | Finnhub | Alpha Vantage | SSI iBoard)
        |
        v
Bronze Layer (Parquet/Iceberg, append, partitioned symbol/year/month)
        |
        v
Silver Layer (cleaned OHLCV + quality report, _errors/)
        |
        v
Gold Layer (94 features: technical + advanced + macro + composite + target)
        |
        +--> Technical Analysis (SMA/EMA/RSI/MACD/Bollinger/ATR/ADX)
        +--> Forecasting (Linear Regression / ARIMA / LSTM)
        +--> Backtesting (MA Crossover / RSI Strategy)
        +--> AI Agent (tool calling) --> Frontend
        |
        v
FastAPI (REST + Swagger)
        |
        v
React + Vite Frontend
```

### Medallion Architecture

| Layer | Mô tả |
|-------|-------|
| **Bronze** | Dữ liệu gần nguồn, append, lineage, duplicate check |
| **Silver** | Chuẩn hóa timezone UTC, ép kiểu, kiểm OHLC/volume, ghi `_errors/` |
| **Gold** | Đặc trưng và target (shift -1, không rò rỉ tương lai) |

### Technologies (theo tầng)

| Tầng | Công nghệ |
|------|-----------|
| API + ORM | Python 3.11, FastAPI, SQLAlchemy 2, Pydantic v2 |
| Migration | Alembic |
| Metadata DB | MySQL 8 (`stock_lakehouse`) |
| Storage | MinIO (S3-compatible) + Apache Parquet |
| Lakehouse catalog | Apache Iceberg REST (SQLite-backed) |
| Streaming | Apache Kafka 3.8 (KRaft mode) |
| ML | scikit-learn, statsmodels, PyTorch |
| AI Agent | Gemini Free API + local tool router |
| Frontend | React 18, Vite 5, TypeScript, Tailwind CSS, TanStack Query |

---

## Tiến độ thực hiện

### Đã hoàn thành

| Module | Trạng thái | Ngày hoàn thành |
|--------|------------|-----------------|
| Docker Infrastructure (mysql + minio + iceberg-rest + kafka) | Hoàn thành | 25/09/2026 |
| MySQL Setup + Alembic migrations | Hoàn thành | 25/09/2026 |
| MinIO Setup (5 buckets) | Hoàn thành | 25/09/2026 |
| Apache Kafka (KRaft mode, 5 topics) | Hoàn thành | 25/09/2026 |
| Apache Iceberg REST Catalog | Hoàn thành | - |
| Lakehouse Architecture (Bronze/Silver/Gold) | Hoàn thành | - |
| Medallion Pipeline orchestrator | Hoàn thành | - |
| FastAPI Backend (15+ endpoints) | Hoàn thành | - |
| React Frontend (Dashboard, Market, Indicators, Forecast, Backtest, Agent) | Hoàn thành | - |
| ML Models (Linear Regression, ARIMA, LSTM) | Hoàn thành | - |
| Backtesting Engine (MA Crossover, RSI Strategy) | Hoàn thành | - |
| AI Agent (Gemini Free + local tool router) | Hoàn thành | - |
| Data Adapter Architecture | Hoàn thành | 29/09/2026 |
| Yahoo Finance Adapter (yfinance package) | Hoạt động | 29/09/2026 |
| Bronze Snapshot Script | Hoạt động | 29/09/2026 |
| Diverse US Stocks (60+ symbols + indexes) | Hoạt động | 29/09/2026 |
| Stock-specific News | Hoạt động | 29/09/2026 |
| **Finnhub Free Provider** (historical + news + profile) | Hoàn thành | 30/09/2026 |
| **YFinancePythonProvider** | Hoàn thành | 30/09/2026 |
| **Historical Ingest Script** (Bronze -> Silver -> Gold) | Hoàn thành | 30/09/2026 |
| **Bootstrap Infrastructure Script** (MinIO buckets + Kafka topics) | Hoàn thành | 30/09/2026 |
| **Finnhub WebSocket Client** (auto-reconnect, PING) | Hoàn thành | 30/09/2026 |
| **StreamPublisher** (WS -> 1s OHLCV -> Kafka) | Hoàn thành | 30/09/2026 |
| **Multi-Source Failover Provider** | Hoàn thành | 30/09/2026 |
| **Iceberg Tables Init Script** (`init_iceberg_tables.py`) | Hoàn thành | 30/09/2026 |
| **Backtest CLI** (`run_backtest.py`) | Hoàn thành | 30/09/2026 |
| **Walk-forward CLI** (`run_walk_forward.py`) | Hoàn thành | 30/09/2026 |
| **Indicator CLI** (`run_indicators.py`) | Hoàn thành | 30/09/2026 |
| **Macro/Regime CLI** (`run_macro_features.py`) | Hoàn thành | 30/09/2026 |
| **AI Agent CLI** (`run_agent.py`) | Hoàn thành | 30/09/2026 |
| **SSI iBoard VN Provider** (`ssi_vn_provider.py`) | Hoàn thành | 30/09/2026 |
| **VN Ingestion CLI** (`ingest_vn.py` - 53 symbols w/ quality report) | Hoàn thành | 30/09/2026 |
| **VN Data Quality Report** (`docs/vn_data_quality.md`) | Hoàn thành | 30/09/2026 |
| **System Health Audit Script** (`tests/_system_audit.py` + `docs/system_health.md`) | Hoàn thành | 01/10/2026 |
| **Route Ordering Fix** (`/data/stocks/supported` 502 → 200) | Hoàn thành | 01/10/2026 |
| **Kafka Producer Compat Fix** (`enable_idempotence` kafka-python <2.5) | Hoàn thành | 01/10/2026 |
| **Kafka Consumer Batch Format Support** (`{"symbol","bars":[...]}`) | Hoàn thành | 01/10/2026 |
| **Web UI End-to-End Test** (tất cả page + AI Agent + Gemini) | Hoàn thành | 01/10/2026 |
| **Vite proxy fix** (`/api/v1` → `127.0.0.1:8000`) | Hoàn thành | 01/10/2026 |
| **Synthetic fallback** (chart demo khi Lakehouse trống) | Hoàn thành | 01/10/2026 |

### TODO - Next Steps

- [ ] Frontend realtime view (consume WS hoặc Kafka topic trực tiếp).
- [ ] Stream consumer chạy nền lâu dài (long-running service).
- [ ] Walk-forward validation across streamed data.
- [ ] Drift detection trên incoming ticks.

---

## Đã hoàn thành

### Docker Setup (25/09/2026)

- Dùng `apache/kafka:3.8.0` ở KRaft mode (không cần ZooKeeper, không cần image private).
- Iceberg REST catalog ở `localhost:8181` (image `tabulario/iceberg-rest:0.9.0`).
- MinIO ở `localhost:9000` (API) + `localhost:9001` (Console).
- MySQL 8 ở `localhost:3307` (mapped từ 3306 trong container).
- 5 Kafka topic: `stock-ohlcv-raw`, `stock-ohlcv-enriched`, `stock-alerts`, `stock-tick`, `stock-candle-1m`.

### Database Schema

- `users` - Tài khoản người dùng (bcrypt password).
- `pipeline_runs` - Lịch sử chạy pipeline.
- `model_runs` - Lịch sử huấn luyện model.
- `backtest_runs` - Lịch sử backtest.
- `agent_conversations` - Lịch sử AI Agent.

### Features

**Dashboard:**
- Giá, % thay đổi, volume.
- RSI, prediction, equity curve.
- Nến, volume chart.
- Pipeline status.

**Market Data:**
- Nến chart.
- Bảng OHLCV.
- CSV export.

**Technical Analysis:**
- SMA, EMA, RSI, MACD, Bollinger Bands, ATR, ADX, Ichimoku, Supertrend, VWAP.
- Bật/tắt indicator.

**Forecasting:**
- Linear Regression, ARIMA, LSTM (PyTorch, CPU).
- Actual vs Predicted chart.
- So sánh 3 model.

**Backtesting:**
- MA Crossover Strategy, RSI Strategy.
- Equity curve, drawdown, trade history.
- Metrics: Total Return, Win Rate, Sharpe Ratio, Max Drawdown, Profit Factor.

**AI Agent:**
- Tool calling vào backend thật (14+ tools).
- Gemini Free API (`gemini-2.0-flash-exp`).
- Local tool router fallback (không cần key).
- Lịch sử chat lưu MySQL `agent_conversations`.

---

## Streaming & Real-time (Finnhub WebSocket + Kafka)

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
| `app/streaming/kafka_producer.py` | Producer Kafka |
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

# 3. Ingest dữ liệu lịch sử (Bronze -> Silver -> Gold)
python scripts/ingest_historical.py --source yfinance --interval 1d
python scripts/ingest_historical.py --source finnhub --symbols AAPL,MSFT --interval 1h

# 4. Train model
python scripts/train_models.py --symbol AAPL --models linear_regression,arima,lstm

# 5. Khởi động publisher (terminal 1)
python scripts/run_stream_publisher.py --symbols AAPL,MSFT,GOOGL

# 6. Khởi động consumer (terminal 2)
python scripts/run_stream_consumer.py --topic stock-ohlcv-raw
```

### Giới hạn Finnhub Free tier

- 1 kết nối WebSocket đồng thời.
- Tối đa 50 symbols subscribe.
- ~50 messages / giây tổng cộng.
- Historical: 1m/5m/15m tối đa 30 ngày; 1h tối đa 365 ngày; daily tối đa 10 năm.

---

## Các lệnh thường dùng

### Docker

```bash
docker compose ps                    # trạng thái container
docker compose logs -f kafka         # log real-time của 1 service
docker compose restart minio         # restart 1 service
docker compose down                  # dừng tất cả (giữ volume)
docker compose down -v               # dừng + XÓA data (cẩn thận)
```

### Backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1

# Migration + bootstrap
python scripts\init_database.py
python scripts\bootstrap_infrastructure.py

# Ingest lịch sử (Bronze -> Silver -> Gold)
python scripts\ingest_historical.py --source multi_source --interval 1d --years 10
python scripts\ingest_vn.py --years 10

# Chạy stream publisher (WebSocket -> Kafka)
python scripts\run_stream_publisher.py --symbols AAPL,MSFT,GOOGL

# Chạy stream consumer (Kafka -> Lakehouse)
python scripts\run_stream_consumer.py --topic stock-ohlcv-raw

# Train models
python scripts\train_models.py --symbol AAPL --models linear_regression,arima,lstm

# Backtest + walk-forward
python scripts\run_backtest.py --symbol AAPL --strategy ma_crossover
python scripts\run_walk_forward.py --symbol AAPL --model lstm --folds 5

# Test AI Agent headless
python scripts\run_agent.py --symbol AAPL --question "RSI hiện tại bao nhiêu?"

# API Server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend

```powershell
cd frontend
npm run dev
```

---

## Cấu hình .env

```bash
# --- Database (MySQL chạy trong Docker, port 3307) ---
MYSQL_HOST=localhost
MYSQL_PORT=3307
MYSQL_USER=root
MYSQL_PASSWORD=123456
MYSQL_DATABASE=stock_lakehouse
DATABASE_URL=mysql+pymysql://root:123456@localhost:3307/stock_lakehouse

# --- Storage ---
STORAGE_BACKEND=minio  # hoặc "local" để fallback filesystem
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# --- Kafka ---
KAFKA_BOOTSTRAP_SERVERS=localhost:9094

# --- Data Source (chọn 1) ---
# - multi_source  : failover chain (yfinance -> finnhub -> alpha_vantage -> web_scraper)
# - yfinance      : official yfinance package
# - finnhub       : Finnhub Free tier (60 req/min)
# - alpha_vantage : Alpha Vantage free tier
# - web_scraper   : Yahoo HTTP + CafeF scrape
DATA_SOURCE=multi_source

# --- Provider API keys (đều free) ---
FINNHUB_API_KEY=<key-từ-finnhub.io>
FINNHUB_WS_SYMBOLS=AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,META,AMD
ALPHA_VANTAGE_API_KEY=<key-từ-alphavantage.co>

# --- AI Agent (Gemini Free - khuyến nghị) ---
LLM_PROVIDER=gemini
GEMINI_API_KEY=<key-từ-aistudio.google.com/apikey>
GEMINI_MODEL=gemini-2.0-flash-exp

# --- Fallback OpenAI (optional) ---
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

Xem đầy đủ biến ở `.env.example` (root) hoặc `backend/.env.example`.

---

## Troubleshooting

| Vấn đề | Cách xử lý |
|--------|-------------|
| MySQL disconnected | Kiểm tra `docker compose ps mysql`, xem log `docker compose logs mysql` |
| `Table 'stock_lakehouse.model_runs' doesn't exist` | Chạy `python scripts\init_database.py` (hoặc `alembic upgrade head`) |
| Không có market data | Đổi `DATA_SOURCE=multi_source` trong `.env`, chạy `ingest_historical.py --source yfinance` |
| MinIO không kết nối | `docker compose ps minio`, đợi healthcheck pass; set `STORAGE_BACKEND=local` để fallback |
| Kafka không healthy | Đợi ~30s cho Kafka khởi động; chạy `scripts\bootstrap_infrastructure.py` |
| Frontend 404 trên `/api/v1/...` | Kiểm tra `frontend/vite.config.ts` proxy `/api/v1` → `http://127.0.0.1:8000` |
| AI Agent trả "no API key" | Đặt `GEMINI_API_KEY` trong `.env`; không có key vẫn chạy được local tool router |
| LSTM chậm | Giảm `LSTM_EPOCHS=20` xuống `5-10`, hoặc dùng model LR / ARIMA cho smoke test |
| Chart rỗng khi chưa ingest | OK - `MarketService` có synthetic fallback (deterministic per ticker) chỉ để demo UI, không ghi vào Lakehouse |
| Finnhub 401/403 | Key mới có thể cần ~5 phút để activate; kiểm tra `FINNHUB_API_KEY` |
| yfinance trả empty | Yahoo rate-limit; nâng cấp `yfinance>=1.0` + `curl_cffi` (đã có trong `requirements.txt`) |
| WebSocket không kết nối | Ping bị block hoặc key sai; kiểm tra `ping finnhub.io` |

---

## Ghi chú

- **$0 budget:** Toàn bộ data layer (yfinance, Finnhub Free tier, Alpha Vantage, SSI iBoard) là miễn phí.
- **Near-real-time:** Finnhub WebSocket (~50 msgs/sec, 50 symbols) + Kafka làm backbone streaming.
- **Không phải production:** Prototype nghiên cứu học thuật.
- **Synthetic fallback chỉ cho demo UI:** Khi Lakehouse chưa populate, `MarketService._synthetic_history()` sinh deterministic OHLCV (252 bars) để chart không trống. Dữ liệu này KHÔNG ghi vào Bronze/Silver/Gold - chỉ là view layer.
