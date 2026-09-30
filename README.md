# Stock Lakehouse AI

Nền tảng prototype khóa luận tốt nghiệp: **Xây dựng nền tảng Data Lakehouse phân tích và dự báo chứng khoán thời gian thực ứng dụng học sâu và AI Agent.**

Toàn bộ dữ liệu OHLCV trong project là dữ liệu thật từ các nguồn free (Yahoo Finance, Finnhub, Alpha Vantage, web scraper). Pipeline Bronze-Silver-Gold chạy qua MinIO, có thể bật PySpark thay cho Pandas, và có luồng streaming qua Kafka.

---

## Academic Disclaimer

Đây là prototype nghiên cứu học thuật.

- Không giao dịch chứng khoán thật
- Không tự động đặt lệnh mua/bán
- Không cam kết lợi nhuận
- Không khẳng định LSTM là mô hình tốt nhất
- Backtesting chỉ đánh giá hiệu suất lịch sử giả định, không phải dự đoán tương lai

---

## Quick Start

### 1. Docker Infrastructure
```bash
docker compose up -d
```

### 2. Backend
```bash
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\bootstrap_infrastructure.py
python scripts\ingest_historical.py --source yfinance --symbols AAPL,MSFT,GOOGL,NVDA
python scripts\init_database.py
uvicorn app.main:app --reload
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

### 4. JupyterLab (Notebooks)
```bash
cd notebooks
jupyter lab
```

---

## Cấu trúc Project

```
stock-lakehouse-ai/
├── backend/              # FastAPI backend
│   ├── app/             # API routes, models, lakehouse
│   ├── scripts/         # Pipelines, ingestion, training
│   └── requirements.txt
├── frontend/            # React + Vite frontend
├── notebooks/           # Jupyter notebooks (EDA, demo)
├── docs/                # Documentation
├── docker-compose.yml   # Docker infrastructure
└── README.md
```

---

## Data Lake Architecture (Medallion)

```
Raw Data -> Bronze -> Silver -> Gold -> ML/Analytics
                |
          MinIO Storage (S3-compatible)
```

| Layer | Mô tả | Storage |
|-------|-------|---------|
| **Bronze** | Raw data, snapshot từ source | `stock-bronze/` |
| **Silver** | Cleaned, enriched, partitioned by symbol/year/month | `stock-silver/` |
| **Gold** | Aggregated features, ML-ready (94 cols / symbol) | `stock-gold/` |

Schema evolution: Bronze append-only, Silver overwrites per partition, Gold overwrites per partition.

---

## Data Sources

### Supported Symbols

**US Stocks (60+):**
```
Technology: AAPL, MSFT, GOOGL, META, NVDA, AMD, ORCL, CRM, ADBE
Finance: JPM, V, MA, GS, BAC, MS, BLK
Consumer: AMZN, TSLA, WMT, HD, NKE, MCD, SBUX
Healthcare: JNJ, UNH, PFE, MRK, ABBV, LLY
Energy: XOM, CVX, COP, SLB
Crypto: COIN, BTC-USD, ETH-USD, MSTR
Vietnam: FPT, MWG, VNM, HPG, VCB, TCB, VIC, VHM, VRE, BID, CTG, EOG, PLX, POW, SAB, SSI
```

**Market Indexes:**
```
^GSPC - S&P 500
^DJI  - Dow Jones
^IXIC - NASDAQ
```

### Adapter Pattern

Mỗi nguồn dữ liệu được đóng gói trong adapter riêng (`app/data_sources/`):

- **YFinancePythonProvider** - `yfinance>=1.0` + `curl_cffi`, real OHLCV, không cần API key
- **FinnhubProvider** - Free tier historical + WebSocket streaming
- **AlphaVantageProvider** - Free tier, fallback khi Yahoo fail
- **WebScraperProvider** - Backup cho VN stocks (VnExpress, Vietstock)
- **MultiSourceProvider** - Failover chain tự động: yfinance -> finnhub -> alpha_vantage -> web_scraper

Đổi nguồn qua biến `DATA_SOURCE` trong `.env`, không cần sửa pipeline.

---

## Features

| Module | Mô tả |
|--------|-------|
| Dashboard | Giá realtime, RSI, prediction, charts (React) |
| Technical Analysis | SMA, EMA, RSI, MACD, Bollinger Bands, ATR, ADX, Ichimoku, Supertrend, VWAP |
| Forecasting | Linear Regression, ARIMA, LSTM với walk-forward validation |
| Backtesting | MA Crossover, RSI Strategy, equity curve, Sharpe ratio |
| AI Agent | Tool calling vào backend thật, 14+ Pydantic tools |
| Data Lake | MinIO + PySpark pipeline + Iceberg REST catalog |
| Streaming | Kafka producer/consumer cho real-time OHLCV |

Gold layer hiện có **94 features** mỗi symbol (technical + advanced + macro + composite).

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11, FastAPI, Pandas, PySpark |
| Frontend | React 18, Vite, TailwindCSS |
| Database | MySQL 8 |
| Storage | MinIO (S3-compatible) |
| Orchestration | Cron-based scheduler (`scripts/schedule_batch.py`) |
| ML | PyTorch, scikit-learn, statsmodels |
| Streaming | Kafka + WebSocket |
| Lakehouse format | Parquet (default) hoặc Apache Iceberg (opt-in) |

---

## Truy cập Dịch vụ

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:5173 | - |
| API | http://localhost:8000 | - |
| Swagger | http://localhost:8000/docs | - |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Adminer (MySQL UI) | http://localhost:8081 | root / 123456 |
| JupyterLab | http://localhost:8888 | Token from terminal |
| Kafka UI | http://localhost:8090 | - |
| Spark Master UI | http://localhost:8080 | - |

---

## Configuration

```bash
# .env
STORAGE_BACKEND=minio       # local hoặc minio
DATA_SOURCE=yfinance        # yfinance, yfinance_direct, finnhub, alpha_vantage, web_scraper, multi_source
USE_SPARK=false             # bật PySpark cho Silver/Gold
USE_KAFKA=false             # bật streaming pipeline
OPENAI_API_KEY=sk-...       # optional, cho AI Agent
```

Xem `.env.example` để biết đầy đủ biến môi trường.

---

## Documentation

| File | Mô tả |
|------|-------|
| [docs/PROGRESS.md](docs/PROGRESS.md) | Progress tracker & setup guide |
| [docs/architecture.md](docs/architecture.md) | Kiến trúc hệ thống |
| [docs/lakehouse.md](docs/lakehouse.md) | Lakehouse (Iceberg/Parquet) |
| [docs/pipeline.md](docs/pipeline.md) | Pipeline & Streaming |
| [docs/database.md](docs/database.md) | MySQL schema |
| [docs/ai_agent.md](docs/ai_agent.md) | AI Agent tools |
| [docs/tech_stack_matrix.md](docs/tech_stack_matrix.md) | Tech-to-file mapping |
| [docs/data_sources.md](docs/data_sources.md) | Data source catalog |

---

## Common Tasks

### Ingest thêm symbols
```bash
python scripts/ingest_historical.py --source yfinance --symbols TSLA,AMZN --interval 1d
```

### Rebuild Gold cho symbols bị lỗi
```bash
python scripts/rebuild_gold.py
```

### Train forecasting model
```bash
python scripts/train_models.py --symbol AAPL --model lstm
```

### Run backtest
```bash
python scripts/run_backtest.py --symbol AAPL --strategy ma_crossover
```

### Walk-forward validation
```bash
python scripts/run_walk_forward.py --symbol AAPL --model lstm --folds 5
```

---

## Data Quality Guarantees

- Tất cả OHLCV trong Gold layer đều từ nguồn thật (Yahoo Finance, Finnhub, Alpha Vantage, hoặc web scraper)
- Không có synthetic/sample data trong production pipeline
- Minimum 5 năm daily data cho mỗi symbol được verify
- Walk-forward validation đảm bảo không có future leakage

Verified datasets (tính tới 2026-09-30):
- AAPL: 2507 rows × 9.99 năm
- MSFT: 1250 rows × ~3.4 năm (Finnhub free tier cap)
- BTC-USD: 3650 rows × 9.99 năm
- ETH-USD: 3247 rows × 8.89 năm
- 102/102 symbols có Gold features built

---

## License

Academic Research Project - Không sử dụng cho mục đích thương mại.

Updated: 2026-09-30 02:24
