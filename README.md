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

**Xem [docs/PROGRESS.md](docs/PROGRESS.md) để biết hướng dẫn chi tiết.**

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

### 4. Truy cập
| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| MinIO Console | http://localhost:9001 |

---

## 📁 Docs

| File | Mô tả |
|------|--------|
| [docs/PROGRESS.md](docs/PROGRESS.md) | **Progress tracker - Hướng dẫn setup & tracking** |
| [docs/architecture.md](docs/architecture.md) | Kiến trúc hệ thống |
| [docs/lakehouse.md](docs/lakehouse.md) | Lakehouse (Iceberg/Parquet) |
| [docs/pipeline.md](docs/pipeline.md) | Pipeline & Streaming |
| [docs/database.md](docs/database.md) | MySQL schema |
| [docs/ai_agent.md](docs/ai_agent.md) | AI Agent tools |

---

## 🏗️ Architecture

```
Stock Data → Ingestion → Bronze → Silver → Gold → ML → API → Frontend/Agent
                           ↓
                     Kafka Streaming
                     MinIO Storage
```

**Medallion:** Bronze (raw) → Silver (cleaned) → Gold (features)

---

## ✨ Features

- 📊 **Dashboard:** Giá, RSI, prediction, charts
- 📈 **Technical Analysis:** SMA, EMA, RSI, MACD, Bollinger
- 🤖 **Forecasting:** Linear Regression, ARIMA, LSTM
- 💹 **Backtesting:** MA Crossover, RSI Strategy, equity curve
- 🤖 **AI Agent:** Tool calling vào backend thật

---

## 🛠️ Tech Stack

Python 3.11 · FastAPI · MySQL 8 · Pandas · PySpark · MinIO · Kafka · Iceberg · PyTorch · React 18 · Vite

---

## ⚙️ Configuration

```bash
# .env
STORAGE_BACKEND=local        # hoặc minio
DATA_SOURCE=sample          # sample hoặc yfinance
USE_SPARK=false
USE_KAFKA=false
OPENAI_API_KEY=sk-...       # optional
```
