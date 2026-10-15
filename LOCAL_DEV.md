# Stock Lakehouse AI — Local Development Guide

> **Source of truth: chạy LOCAL. Docker Compose là bước SAU, khi code đã ổn.**

Project này được thiết kế để dev nhanh trên local (no Docker). Mọi sửa code
đều thấy ngay mà không cần rebuild image. Khi sẵn sàng demo, dùng
`docker compose` để có 1 lệnh spin up toàn bộ stack.

---

## TL;DR — Chạy trong 1 lệnh

```powershell
# Từ D:\School\kltn\stock-lakehouse-ai
powershell -ExecutionPolicy Bypass -File .\start-all.ps1
```

Mở browser: **http://127.0.0.1:5173**

Dừng:
```powershell
powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
```

---

## Cấu trúc repo

```
stock-lakehouse-ai/
├── backend/                 # FastAPI (Python 3.11+)
│   ├── .env                 # Canonical config (Docker hostnames)
│   ├── .env.local           # ⚠️  TỰ TẠO, override cho local (gitignore)
│   ├── .env.local.example   # Template để copy
│   ├── .venv/               # Python virtualenv
│   └── app/
│       ├── api/             # REST routes
│       ├── core/            # config, logging, db
│       ├── lakehouse/       # Bronze/Silver/Gold storage
│       ├── streaming/       # Kafka producers/publishers
│       └── ...
├── frontend/                # Vite + React + TypeScript
│   ├── .env                 # Vite env
│   └── src/
├── docker-compose.yml       # Dùng SAU, khi code đã ổn
├── start-all.{ps1,bat}      # Launcher local
└── stop-all.{ps1,bat}       # Killer local
```

---

## Setup lần đầu (chỉ làm 1 lần)

### 1. Tạo file `.env.local`

Backend đọc `.env` (canonical) trước, sau đó override bằng `.env.local`
(nếu có). File này chứa config **của máy bạn**, không commit lên git.

```powershell
cd backend
Copy-Item .env.local.example .env.local
# Sửa .env.local nếu cần (port MySQL/Kafka khác mặc định, có API key, ...)
```

Mặc định `.env.local.example` đã chuẩn cho local dev:
- MySQL: `127.0.0.1:3306`
- Storage: `local` (không cần MinIO)
- Kafka: **tắt** (set `USE_KAFKA=false` để chạy được không cần Kafka)
- Pollers (EOD/crawler/WS): **tắt** cho đỡ tốn CPU

### 2. Khởi động các dịch vụ CẦN THIẾT

#### MySQL (bắt buộc cho backend lưu metadata)

Option A — đã cài local:
```powershell
# Service phải đang chạy, port 3306, user root/123456
# Tạo schema:
mysql -u root -p123456 -e "CREATE DATABASE IF NOT EXISTS stock_lakehouse;"
```

Option B — dùng Docker cho MỖI MySQL riêng (vẫn là "local dev", chỉ 1 container):
```powershell
docker run -d --name local-mysql -p 3306:3306 `
  -e MYSQL_ROOT_PASSWORD=123456 `
  -e MYSQL_DATABASE=stock_lakehouse `
  mirror.gcr.io/library/mysql:8.4
```

#### Kafka + MinIO (chỉ cần nếu bật streaming)

```powershell
docker run -d --name local-kafka -p 9094:9094 `
  -e KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093,EXTERNAL://:9094 `
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092,EXTERNAL://localhost:9094 `
  -e KAFKA_PROCESS_ROLES=controller,broker `
  -e KAFKA_NODE_ID=1 `
  -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER `
  -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 `
  -e KAFKA_INTER_BROKER_LISTENER_NAME=PLAINTEXT `
  -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,EXTERNAL:PLAINTEXT `
  -e KAFKA_AUTO_CREATE_TOPICS_ENABLE=true `
  apache/kafka:3.8.0
```

Nếu KHÔNG muốn cài Kafka, để `USE_KAFKA=false` trong `.env.local` — backend
vẫn chạy được, chỉ thiếu streaming real-time.

---

## Chạy hàng ngày

### Script tự động (khuyến nghị)

```powershell
# Từ thư mục gốc project
.\start-all.bat
```

Hai cửa sổ cmd sẽ bật lên:
- `Stock-LH-Backend` (FastAPI :8000)
- `Stock-LH-Frontend` (Vite :5173)

Đóng 2 cửa sổ đó = tắt stack. Hoặc chạy `.\stop-all.bat` để kill từ launcher.

### Chạy thủ công (2 PowerShell riêng)

```powershell
# Terminal 1 - Backend
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
# Terminal 2 - Frontend
cd frontend
npm run dev
```

---

## URL map (local)

| Service       | URL                              |
|---------------|----------------------------------|
| Frontend SPA  | http://127.0.0.1:5173            |
| Agent UI      | http://127.0.0.1:5173/agent      |
| Backend API   | http://127.0.0.1:8000            |
| API docs      | http://127.0.0.1:8000/docs       |
| Health check  | http://127.0.0.1:8000/api/v1/health |

---

## Từ local sang Docker (khi code đã ổn)

Khi đã chạy local ổn ≥ 1 ngày không regress:

```powershell
# Bật Docker daemon (lightweight, không cần Desktop UI)
powershell -ExecutionPolicy Bypass -File .\start-docker-daemon.ps1

# Build + start toàn bộ stack
.\make.ps1 up-all
# hoặc: docker compose --profile all up -d --build

# Verify (~90s sau khi build xong)
.\make.ps1 health
```

Xem `docker-cheatsheet.md` để biết thêm lệnh Docker hữu ích.

---

## Troubleshooting

### Backend không start, lỗi "Can't connect to MySQL"
- Kiểm tra MySQL đang chạy: `netstat -ano | findstr :3306`
- Nếu port khác 3306, sửa `MYSQL_PORT` trong `backend/.env.local`
- Test thử: `python -c "import pymysql; pymysql.connect(host='127.0.0.1', port=3306, user='root', password='123456')"`

### Frontend không load được API
- Mở DevTools (F12) → tab Network
- Nếu thấy 404 với `/api/v1/...`, kiểm tra `frontend/.env` có `VITE_API_BASE_URL=http://localhost:8000/api/v1` (default đã đúng)
- Restart Vite sau khi sửa `.env` (Vite không hot-reload env)

### `.env.local` không có tác dụng
- Đảm bảo file nằm đúng chỗ: `backend/.env.local` (không phải `frontend/`)
- Restart backend sau khi sửa
- Test: `cd backend; python -c "from app.core.config import settings; print(settings.mysql_host)"` phải in ra `127.0.0.1`

### Port bị chiếm
- Backend (8000): `Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process -Force`
- Frontend (5173): tương tự với port 5173

---

## Khi nào dùng gì?

| Tình huống                          | Dùng     |
|-------------------------------------|----------|
| Sửa code Python/TS, test nhanh      | **Local** |
| Train model, backtest, demo API     | **Local** |
| Chạy 1-2 service riêng (vd: Kafka)  | **Local** |
| Demo cho GV, cần stack ổn định      | Docker   |
| CI/CD, môi trường production       | Docker   |
| Test failover / multi-instance      | Docker   |
