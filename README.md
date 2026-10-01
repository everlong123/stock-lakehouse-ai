# Stock Lakehouse AI

Nền tảng prototype khóa luận tốt nghiệp:

**Xây dựng nền tảng Data Lakehouse phân tích và dự báo chứng khoán ứng dụng học sâu và AI Agent.**

Toàn bộ dữ liệu OHLCV trong project là dữ liệu thật từ các nguồn free (Yahoo Finance, Finnhub, Alpha Vantage, SSI iBoard cho cổ phiếu Việt Nam). Pipeline Bronze - Silver - Gold chạy trên MinIO (S3-compatible), catalog quản lý schema bằng Apache Iceberg REST. Backend FastAPI expose dữ liệu + model + backtest, frontend React/Vite hiển thị dashboard, và AI Agent dùng Gemini Free API để trả lời câu hỏi tự nhiên qua tool calling vào chính backend.

---

## Academic Disclaimer

Đây là prototype nghiên cứu học thuật.

- Không giao dịch chứng khoán thật.
- Không tự động đặt lệnh mua/bán.
- Không cam kết lợi nhuận.
- Không khẳng định LSTM là mô hình tốt nhất.
- Backtesting chỉ đánh giá hiệu suất lịch sử giả định, không phải dự đoán tương lai.

---

## Tech Stack (công nghệ nào có trong đồ án)

| Tầng | Công nghệ | Vai trò |
|------|-----------|---------|
| **Backend API** | Python 3.11, FastAPI, Pydantic v2 | REST API (`/api/v1/...`) |
| **ORM / Migration** | SQLAlchemy 2, Alembic | Metadata MySQL + schema version |
| **Metadata DB** | MySQL 8 (`stock_lakehouse`) | Lưu `users`, `pipeline_runs`, `model_runs`, `backtest_runs`, `agent_conversations` |
| **Object Storage** | MinIO (S3-compatible) | Bucket `stock-bronze`, `stock-silver`, `stock-gold`, `stock-models`, `stock-backtests` |
| **Lakehouse format** | Apache Parquet + Apache Iceberg (REST catalog) | Partition theo `symbol/year/month`, time-travel |
| **Stream engine** | Apache Kafka 3.8 (KRaft mode) | Topic `stock-ohlcv-raw`, `stock-tick`, `stock-alerts`... |
| **ML / Forecasting** | scikit-learn, statsmodels (ARIMA), PyTorch (LSTM) | Train/predict LR, ARIMA, LSTM |
| **Backtest** | Engine tự viết (`app/backtesting/`) | MA Crossover, RSI Strategy, Sharpe / Drawdown |
| **AI Agent** | Gemini Free API (`gemini-2.0-flash-exp`) + tool router | Tool calling vào backend thật |
| **Data sources** | yfinance, Finnhub, Alpha Vantage, SSI iBoard | Multi-provider + failover |
| **Frontend** | React 18, Vite 5, TypeScript, TailwindCSS, TanStack Query, Recharts, Lucide | Dashboard, indicator, forecast, backtest, agent chat |
| **Container** | Docker Compose | mysql, minio, iceberg-rest, kafka |

---

## Cấu trúc Project

```
stock-lakehouse-ai/
├── backend/
│   ├── app/                    # FastAPI app, lakehouse, forecasting, agent, streaming
│   ├── scripts/                # CLI scripts (ingest, bootstrap, train, backtest, agent)
│   ├── alembic/                # Database migrations
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── src/                    # React app
│   ├── .env                    # VITE_API_BASE_URL
│   └── package.json
├── docs/                       # Documentation (architecture, lakehouse, ai agent, ...)
├── docker-compose.yml          # mysql + minio + iceberg-rest + kafka
├── .env                        # Backend env (MySQL/MinIO/Kafka/API keys)
└── README.md
```

---

## Quick Start (5 bước)

### Bước 0 - Yêu cầu môi trường

| Phần mềm | Phiên bản | Ghi chú |
|----------|-----------|---------|
| Docker Desktop | 4.x trở lên | Bắt buộc cho MySQL/MinIO/Iceberg/Kafka |
| Python | 3.11 | Tạo venv trong `backend/.venv` |
| Node.js | 18 hoặc 20 LTS | Cho frontend Vite |
| Git | bất kỳ | Clone repo |

> Toàn bộ 4 service infra chạy bằng Docker Compose. Backend Python chạy local (không cần Docker cho app). Frontend chạy local qua `npm run dev`.

### Bước 1 - Khởi động Docker Infrastructure

```bash
# tại thư mục gốc stock-lakehouse-ai/
docker compose up -d
docker compose ps
```

Sau ~20-30 giây, 4 container sau phải ở trạng thái `running`/`healthy`:

| Service | Container | Port (host) | URL quản lý |
|---------|-----------|-------------|-------------|
| MySQL 8 | stock-lakehouse-mysql | 3307 | (không có UI; dùng CLI hoặc MySQL client) |
| MinIO | stock-lakehouse-minio | 9000 (API), 9001 (Console) | http://localhost:9001 (minioadmin / minioadmin) |
| Iceberg REST | stock-lakehouse-iceberg-rest | 8181 | http://localhost:8181/v1/config |
| Apache Kafka | stock-lakehouse-kafka | 9092 (internal), 9094 (external) | (không có UI) |

Nếu container nào báo `unhealthy`, đợi thêm 15-30s rồi `docker compose ps` lại. Nếu Kafka lâu healthy, kiểm tra log: `docker compose logs -f kafka`.

### Bước 2 - Cấu hình `.env`

File `.env` ở thư mục gốc và `backend/.env` đã có sẵn các giá trị mặc định để chạy local. Các biến quan trọng cần kiểm tra:

```bash
# .env (root) hoặc backend/.env
MYSQL_HOST=localhost
MYSQL_PORT=3307
MYSQL_PASSWORD=123456
DATABASE_URL=mysql+pymysql://root:123456@localhost:3307/stock_lakehouse

STORAGE_BACKEND=minio
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Data source
DATA_SOURCE=multi_source    # yfinance -> finnhub -> alpha_vantage -> web_scraper
FINNHUB_API_KEY=<optional>  # free tại https://finnhub.io/
ALPHA_VANTAGE_API_KEY=<optional>  # free tại https://www.alphavantage.co/support/#api-key

# AI Agent
LLM_PROVIDER=gemini
GEMINI_API_KEY=<free-key-from-aistudio.google.com>
GEMINI_MODEL=gemini-2.0-flash-exp
```

> Cả `.env` ở root và `backend/.env` đều được đọc. `backend/.env` sẽ override các biến tương ứng.

### Bước 3 - Backend (FastAPI)

```powershell
cd backend

# tạo venv lần đầu
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

# cài dependencies
pip install -r requirements.txt

# tạo database + chạy Alembic migrations (idempotent)
python scripts\init_database.py

# (optional) tạo MinIO buckets + Kafka topics
python scripts\bootstrap_infrastructure.py

# (optional) ingest dữ liệu lịch sử thật (5-10 năm)
python scripts\ingest_historical.py --source multi_source --years 10
python scripts\ingest_vn.py --years 10        # cổ phiếu VN qua SSI

# chạy API server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Sau khi server lên, kiểm tra:

- Swagger UI: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/v1/health
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

### Bước 4 - Frontend (React + Vite)

```powershell
cd frontend
npm install
# .env đã có sẵn VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
npm run dev
```

Frontend chạy tại: **http://127.0.0.1:5173**.

Vite đã được cấu hình proxy `/api/v1` -> `http://127.0.0.1:8000`, nên có thể gọi API trực tiếp từ browser qua `/api/v1/...` mà không cần CORS.

### Bước 5 - Truy cập nhanh

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend (web app) | http://127.0.0.1:5173 | - |
| Backend Swagger | http://127.0.0.1:8000/docs | - |
| Backend Health | http://127.0.0.1:8000/api/v1/health | - |
| MinIO Console | http://127.0.0.1:9001 | minioadmin / minioadmin |
| Iceberg REST | http://127.0.0.1:8181/v1/config | - |

---

## Data Lake Architecture (Medallion)

```
Real sources (yfinance / Finnhub / Alpha Vantage / SSI iBoard)
        |
        v
   Bronze (raw OHLCV, append-only, partitioned symbol/year/month)
        |
        v
   Silver (cleaned UTC, OHLC validated, dedupe, _errors/)
        |
        v
   Gold (94 features: technical + advanced + macro + composite + target)
        |
        +--> Technical Analysis (SMA/EMA/RSI/MACD/Bollinger/ATR/ADX/Ichimoku)
        +--> Forecasting (Linear Regression / ARIMA / LSTM)
        +--> Backtesting (MA Crossover, RSI Strategy)
        +--> AI Agent (tool calling) --> Frontend
```

Mỗi layer được giải thích chi tiết trong [`docs/lakehouse.md`](docs/lakehouse.md) và [`docs/PROGRESS_LAKEHOUSE.md`](docs/PROGRESS_LAKEHOUSE.md).

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

### Backend (Python)

```powershell
cd backend
.\.venv\Scripts\Activate.ps1

# Migration MySQL
python scripts\init_database.py

# Tạo MinIO buckets + Kafka topics
python scripts\bootstrap_infrastructure.py

# Ingest dữ liệu thật
python scripts\ingest_historical.py --source yfinance --symbols AAPL,MSFT,GOOGL,NVDA --years 10
python scripts\ingest_vn.py --years 10

# Chạy pipeline Bronze -> Silver -> Gold cho 1 symbol
python scripts\run_pipeline.py --symbol AAPL

# Train + backtest + walk-forward
python scripts\train_models.py --symbol AAPL --models linear_regression,arima,lstm
python scripts\run_backtest.py --symbol AAPL --strategy ma_crossover
python scripts\run_walk_forward.py --symbol AAPL --model lstm --folds 5

# Test AI Agent headless
python scripts\run_agent.py --symbol AAPL --question "RSI hiện tại bao nhiêu?"

# API server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend

```powershell
cd frontend
npm install         # lần đầu
npm run dev         # dev server (http://127.0.0.1:5173)
npm run build       # build production (tsc + vite build)
npm run preview     # preview production build
```

---

## API Endpoints chính

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/v1/health` | Health check tổng |
| GET | `/api/v1/system/status` | Trạng thái bronze/silver/gold + providers |
| GET | `/api/v1/stocks/symbols` | Danh sách symbol đã ingest |
| GET | `/api/v1/stocks/{symbol}?interval=1d&limit=500` | Lịch sử OHLCV |
| GET | `/api/v1/stocks/{symbol}/latest` | Bar mới nhất |
| GET | `/api/v1/stocks/{symbol}/indicators` | SMA/EMA/RSI/MACD/Bollinger |
| GET | `/api/v1/dashboard/{symbol}` | Bundle data cho dashboard |
| POST | `/api/v1/forecast/train` | Train model (LR/ARIMA/LSTM) |
| POST | `/api/v1/forecast/predict` | Predict N-day |
| GET | `/api/v1/forecast/compare/{symbol}` | So sánh 3 model |
| POST | `/api/v1/backtests/run` | Chạy 1 backtest |
| GET | `/api/v1/backtests/history` | Lịch sử backtest |
| POST | `/api/v1/agent/chat` | Chat với AI Agent |
| POST | `/api/v1/pipeline/run` | Chạy Bronze -> Silver -> Gold |

Đầy đủ ở Swagger: <http://127.0.0.1:8000/docs>.

---

## Cấu hình chi tiết

### AI Agent (Gemini Free)

1. Lấy API key miễn phí tại <https://aistudio.google.com/apikey> (60 req/min, không cần thẻ).
2. Đặt vào `.env`:
   ```
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=<key-của-bạn>
   GEMINI_MODEL=gemini-2.0-flash-exp
   ```
3. Không có key, Agent vẫn chạy được bằng local tool router (vẫn gọi đúng backend tools, không bịa số).

### Data Sources (free)

| Source | Key? | Dùng cho | Cách lấy |
|--------|------|----------|----------|
| yfinance | Không | US stocks + crypto + indexes | `pip install yfinance` (đã có sẵn) |
| Finnhub | Có (free) | US stocks + WS streaming | <https://finnhub.io/> |
| Alpha Vantage | Có (free) | Fallback daily OHLCV | <https://www.alphavantage.co/support/#api-key> |
| SSI iBoard | Không | Cổ phiếu VN (HOSE/HNX/UPCOM) | Public API của SSI |
| Multi-source | Auto | Failover chain | Set `DATA_SOURCE=multi_source` |

### Storage

- `STORAGE_BACKEND=minio` (mặc định): dùng MinIO container đang chạy ở `localhost:9000`.
- `STORAGE_BACKEND=local`: fallback về `backend/data/` nếu MinIO lỗi. Không cần Docker để dev nhanh.

### Streaming (Kafka)

- `docker compose up -d kafka` đã bật Kafka ở KRaft mode (không cần ZooKeeper).
- `scripts/bootstrap_infrastructure.py` tạo các topic: `stock-ohlcv-raw`, `stock-ohlcv-enriched`, `stock-alerts`, `stock-tick`, `stock-candle-1m`.
- Producer / consumer chạy qua:
  ```powershell
  python scripts\run_stream_publisher.py --symbols AAPL,MSFT
  python scripts\run_stream_consumer.py --topic stock-ohlcv-raw
  ```

---

## Data Quality Guarantees

- Tất cả OHLCV trong Gold layer đều từ nguồn thật (yfinance / Finnhub / Alpha Vantage / SSI iBoard). Không có synthetic data trong production pipeline.
- Minimum 5 năm daily data cho mỗi symbol được verify.
- Walk-forward validation đảm bảo không có future leakage (chia time-series, target dùng `shift(-1)`).
- Khi Lakehouse trống, `MarketService` có fallback synthetic deterministic (chỉ cho demo UI, không ghi vào Bronze/Silver/Gold) để chart không bị trống.

Verified datasets (snapshot 2026-09-30):
- US stocks (AAPL, MSFT, GOOGL, NVDA, ...): ~2500 rows × ~10 năm mỗi mã.
- Crypto (BTC-USD, ETH-USD): 3000-3650 rows × 8-10 năm.
- VN stocks (VCB, FPT, HPG, MWG, ...): 50/53 symbols × 5-10 năm (xem `docs/vn_data_quality.md`).

---

## Documentation

| File | Mô tả |
|------|-------|
| [docs/PROGRESS_LAKEHOUSE.md](docs/PROGRESS_LAKEHOUSE.md) | Báo cáo tiến độ chi tiết cho thầy (Bronze/Silver/Gold + demo) |
| [docs/PROGRESS.md](docs/PROGRESS.md) | Progress tracker tổng + setup guide |
| [docs/architecture.md](docs/architecture.md) | Kiến trúc tổng thể |
| [docs/lakehouse.md](docs/lakehouse.md) | Chi tiết Bronze/Silver/Gold + Iceberg |
| [docs/pipeline.md](docs/pipeline.md) | Pipeline orchestrator + streaming |
| [docs/database.md](docs/database.md) | MySQL schema (metadata) |
| [docs/ai_agent.md](docs/ai_agent.md) | AI Agent tools + Gemini config |
| [docs/data_sources.md](docs/data_sources.md) | Catalog data sources free |
| [docs/tech_stack_matrix.md](docs/tech_stack_matrix.md) | Map công nghệ -> file implementation |
| [docs/vn_data_quality.md](docs/vn_data_quality.md) | Quality report cho cổ phiếu VN |
| [docs/system_health.md](docs/system_health.md) | System health audit (sau khi chạy audit script) |

---

## License

Academic Research Project - Không sử dụng cho mục đích thương mại.
