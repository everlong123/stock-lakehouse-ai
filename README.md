# Stock Lakehouse AI

Nền tảng prototype khóa luận: **Xây dựng nền tảng Data Lakehouse phân tích và dự báo chứng khoán thời gian thực ứng dụng học sâu và AI Agent.**

---

## ⚠️ Academic Disclaimer

Đây là prototype nghiên cứu học thuật.

- ❌ Không giao dịch chứng khoán thật
- ❌ Không tự động đặt lệnh mua/bán
- ❌ Không cam kết lợi nhuận
- ❌ Không khẳng định LSTM chắc chắn tốt nhất
- ❌ Backtesting chỉ đánh giá hiệu suất lịch sử giả định

---

## 🚀 Quick Start

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
python scripts\generate_sample_data.py
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

## 📁 Cấu trúc Project

```
stock-lakehouse-ai/
├── backend/              # FastAPI backend
│   ├── app/             # API routes, models, lakehouse
│   ├── adapters/        # Data source adapters
│   ├── scripts/         # Data generation, pipelines
│   └── requirements.txt
├── frontend/            # React + Vite frontend
├── notebooks/           # Jupyter notebooks (PySpark, EDA)
├── dagster/             # Dagster orchestration
├── docs/                # Documentation
├── docker-compose.yml   # Docker infrastructure
└── README.md
```

---

## 🗄️ Data Lake Architecture (Medallion)

```
Raw Data → Bronze → Silver → Gold → ML/Analytics
              ↓
        MinIO Storage (S3-compatible)
```

| Layer | Mô tả | Storage |
|-------|-------|---------|
| **Bronze** | Raw data, snapshot từ source | `stock-bronze/` |
| **Silver** | Cleaned, enriched, partitioned | `stock-silver/` |
| **Gold** | Aggregated features, ML-ready | `stock-gold/` |

---

## 📊 Data Sources

### Supported Symbols

**US Stocks:**
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

### Adapter Pattern

Mỗi nguồn dữ liệu được đóng gói trong adapter riêng:
- **Swap dễ dàng:** Thay nguồn không sửa pipeline
- **Fallback:** MultiSourceAdapter thử từng nguồn
- **Bronze snapshot:** Lưu raw data để đảm bảo chạy được

---

## ✨ Features

- 📊 **Dashboard:** Giá, RSI, prediction, charts
- 📈 **Technical Analysis:** SMA, EMA, RSI, MACD, Bollinger Bands
- 🤖 **Forecasting:** Linear Regression, ARIMA, LSTM
- 💹 **Backtesting:** MA Crossover, RSI Strategy, equity curve
- 🤖 **AI Agent:** Tool calling vào backend thật
- 🗄️ **Data Lake:** MinIO + PySpark pipeline

---

## 🛠️ Tech Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.11, FastAPI, Pandas, PySpark |
| Frontend | React 18, Vite, TailwindCSS |
| Database | MySQL 8 |
| Storage | MinIO (S3-compatible) |
| Orchestration | Dagster |
| ML | PyTorch, scikit-learn |
| Streaming | Kafka |

---

## 📂 Truy cập Dịch vụ

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:5173 | - |
| API | http://localhost:8000 | - |
| Swagger | http://localhost:8000/docs | - |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| JupyterLab | http://localhost:8888 | Token from terminal |

---

## ⚙️ Configuration

```bash
# .env
STORAGE_BACKEND=minio      # local hoặc minio
DATA_SOURCE=sample         # sample hoặc yfinance
USE_SPARK=false
USE_KAFKA=false
OPENAI_API_KEY=sk-...     # optional
```

---

## 📖 Documentation

Xem [docs/PROGRESS.md](docs/PROGRESS.md) để biết hướng dẫn chi tiết.

| File | Mô tả |
|------|-------|
| [docs/PROGRESS.md](docs/PROGRESS.md) | Progress tracker & setup guide |
| [docs/architecture.md](docs/architecture.md) | Kiến trúc hệ thống |
| [docs/lakehouse.md](docs/lakehouse.md) | Lakehouse (Iceberg/Parquet) |
| [docs/pipeline.md](docs/pipeline.md) | Pipeline & Streaming |
| [docs/database.md](docs/database.md) | MySQL schema |
| [docs/ai_agent.md](docs/ai_agent.md) | AI Agent tools |

---

## 📜 License

Academic Research Project - Không sử dụng cho mục đích thương mại.

Updated: 2026-09-29 19:32
