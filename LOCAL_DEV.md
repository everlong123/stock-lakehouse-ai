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
│   ├── .env.local           # TỰ TẠO, override cho local (gitignore)
│   ├── .env.local.example   # Template để copy
│   ├── .venv/               # Python virtualenv
│   └── app/
│       ├── api/             # REST routes
│       ├── core/            # config, logging, db
│       ├── lakehouse/       # Bronze/Silver/Gold storage
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
# Sửa .env.local nếu cần (port MySQL/MinIO khác mặc định, có API key, ...)
```

Mặc định `.env.local.example` đã chuẩn cho local dev:
- MySQL: `127.0.0.1:3306`
- Storage: `local` (không cần MinIO)
- Pollers (EOD/crawler/WS): **tắt** cho đỡ tốn CPU

> **Không còn Kafka.** Apache Kafka bị gỡ khỏi dự án ngày 10/11/2026:
> batch pipeline đọc thẳng từ provider, không cần message broker. Biến
> `USE_KAFKA` / `KAFKA_BOOTSTRAP_SERVERS` đã bị xoá khỏi `app/core/config.py`.

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

#### MinIO (chỉ cần nếu bật `STORAGE_BACKEND=minio`)

```powershell
docker run -d --name local-minio -p 9000:9000 -p 9001:9001 `
  -e MINIO_ROOT_USER=minioadmin `
  -e MINIO_ROOT_PASSWORD=minioadmin `
  minio/minio server /data --console-address ":9001"
```

> **Không còn Kafka.** Apache Kafka bị gỡ khỏi dự án ngày 10/11/2026.
> Batch pipeline đọc thẳng từ provider (Yahoo / yfinance / Finnhub /
> SSI iBoard), nên không cần message broker nào cả.
>
> **Không còn realtime/tick.** Toàn bộ đường dẫn real-time (cache trong RAM
> phục vụ SSE, hai client WebSocket Finnhub + SSI iBoard) bị gỡ ngày
> 11/11/2026. Dữ liệu duy nhất là **bar NGÀY** do cron nạp vào Bronze.
> Mọi giá hiển thị trên web đều là giá đóng cửa đã lưu trong lakehouse.

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

### Docker trong WSL2 — hạ tầng "tự chết" giữa chừng

Nếu MySQL/MinIO trong WSL2 không truy cập được (`WinError 10061`), hoặc
`docker ps` luôn hiện `"Up 3 seconds"`, hoặc backend log ghi
`Falling back to local storage` — hãy làm theo thứ tự:

**Bước 1 — Bật lại Scheduled Task giữ WSL sống.**

WSL2 tắt VM khi client `wsl.exe` cuối cùng thoát, kéo theo Docker dừng. Task
`WSL-Distro-Keepalive` giữ một session mở, nhưng nó có thể bị `Disabled`:

```powershell
Get-ScheduledTask -TaskName "WSL-Distro-Keepalive" | Select TaskName, State
# Bị:  State = Disabled   -> cần bật
Enable-ScheduledTask -TaskName "WSL-Distro-Keepalive"
Start-ScheduledTask -TaskName "WSL-Distro-Keepalive"
Get-ScheduledTask -TaskName "WSL-Distro-Keepalive" | Select State   # -> Running
```

Sau đó kiểm tra có client WSL nào attach không (phải ≥ 1):

```powershell
(Get-CimInstance Win32_Process -Filter "Name='wsl.exe'" | Measure-Object).Count
```

**Bước 2 — Bật Docker daemon và container.**

```powershell
wsl -d Ubuntu-24.04 -u root -e bash -c "systemctl start docker"
wsl -d Ubuntu-24.04 -u root -e bash -c \
  "cd /mnt/d/School/kltn/stock-lakehouse-ai && docker compose up -d mysql minio"
```

**Bước 3 — Bật relay và lấy IP WSL hiện tại.**

```powershell
wsl -d Ubuntu-24.04 -u root -e bash -c \
  "systemctl start stock-relay; python3 backend/scripts/start_relay.py --no-spawn"
wsl -d Ubuntu-24.04 -u root -e bash -c "cat /tmp/relay_endpoints.txt"
```

**Bước 4 — Trỏ `backend/.env.local` vào IP vừa lấy.**

```properties
MYSQL_HOST=<ip-vua-wsl>
MINIO_ENDPOINT=<ip-vua-wsl>:19000
DATABASE_URL=mysql+pymysql://root:123456@<ip-vua-wsl>:13307/stock_lakehouse
```

> **Vì sao dùng IP WSL chứ không `127.0.0.1`?** Đo ngày 17/11/2026: gọi
> `127.0.0.1:13307` từ Windows bị từ chối, còn gọi theo IP của VM thì thông.
> Đổi lại IP **đổi mỗi lần `wsl --shutdown`**, nên phải làm lại Bước 3–4 sau
> mỗi lần restart WSL.

**Bước 5 — Khởi động lại backend** (nó đã cache trạng thái fallback local):

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Kiểm tra đã đúng chưa:

```powershell
Select-String -Path backend\logs\*.err -Pattern "storage backend"
# Đúng: "Using MinIO storage backend"
# Sai:  "Falling back to local storage"
```

> **Cảnh báo quan trọng:** khi backend fallback sang local storage, nó **vẫn trả
> HTTP 200** nhưng với dữ liệu *rỗng*. `GET /api/v1/stocks/AAPL/latest` sẽ trả
> 404 dù dữ liệu có thật trong MinIO. Kiểm tra dữ liệu thật thẳng:
>
> ```powershell
> cd backend; .\.venv\Scripts\python.exe -c "from minio import Minio; c=Minio('<ip>:19000',access_key='minioadmin',secret_key='minioadmin',secure=False); print([b.name for b in c.list_buckets()])"
> ```

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
| Chạy 1-2 service riêng (vd: MinIO)  | **Local** |
| Demo cho GV, cần stack ổn định      | Docker   |
| CI/CD, môi trường production       | Docker   |
| Test failover / multi-instance      | Docker   |
