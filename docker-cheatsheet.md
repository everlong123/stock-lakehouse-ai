# Docker Cheatsheet (Windows CMD)

Tài liệu tham chiếu nhanh để chạy project `stock-lakehouse-ai` trên Windows bằng CMD.
Mọi lệnh đều chạy trong **CMD as Administrator** (trừ những lệnh được đánh dấu `[user]`).

> **Trạng thái stack hiện tại (đo ngày 10/11/2026):** dự án **không còn Kafka và Iceberg**.
> Kiến trúc hiện là: MySQL + MinIO + backend + frontend + **scheduler** (cron chạy batch).
> Lệnh Kafka cũ đã bị gỡ khỏi file này.

---

## 1. Khởi động Docker daemon (không UI — nhẹ cho máy RAM yếu)

> Nếu bạn đã mở Docker Desktop bình thường thì bỏ qua bước này.

```cmd
cd /d D:\School\kltn\stock-lakehouse-ai
start-docker-daemon.bat
```

Đợi dòng `Docker daemon is up` (~30-60s).

**Tắt daemon** (giải phóng RAM):
```cmd
taskkill /F /IM dockerd.exe
```

---

## 2. Khởi động toàn bộ stack (lần đầu hoặc sau khi tắt máy)

```cmd
cd /d D:\School\kltn\stock-lakehouse-ai
docker compose --profile all up -d --build
```

> Lần đầu build image mất 5-15 phút (image `backend` cài PyTorch nên nặng nhất). Lần sau (đã có image) mất 5-30 giây.

**Các profile có sẵn** (`docker-compose.yml`):

| Profile | Chạy những gì |
|---|---|
| `infra` | mysql, minio |
| `app` | mysql, minio, backend, frontend, scheduler |
| `all` | tất cả (mặc định cho demo) |
| `minimal` | mysql, minio, backend, frontend (nhẹ nhất) |

**Chỉ chạy 1 container** (không build lại):
```cmd
docker compose --profile all up -d scheduler
```

---

## 3. Restart container (sau khi sửa `.env` hoặc code)

**Restart nhẹ** (giữ image, không build lại — nhanh nhất):
```cmd
docker compose --profile all restart backend
docker compose --profile all restart scheduler
```

**Restart + rebuild** (khi sửa code Python):
```cmd
docker compose --profile all up -d --build backend
```

> `scheduler` dùng **chung image** với `backend` (`stock-lakehouse-backend:latest`), nên khi build lại `backend` thì container `scheduler` cũng cần được khởi động lại để nhận code mới:
> ```cmd
> docker compose --profile all up -d --build backend scheduler
> ```

---

## 4. Kiểm tra trạng thái

```cmd
docker ps                              REM các container đang chạy
docker ps -a                           REM tất cả (kể cả đã dừng)
docker compose --profile all ps        REM chỉ container của project này
docker info                            REM thông tin Docker daemon
```

---

## 5. Xem logs

```cmd
REM Logs mới nhất của 1 container
docker compose --profile all logs --tail=100 backend

REM Follow logs realtime (Ctrl+C để dừng)
docker compose --profile all logs -f backend

REM Nhiều container cùng lúc
docker compose --profile all logs -f --tail=50 backend frontend

REM Lọc theo keyword (vd: lỗi)
docker compose --profile all logs --tail=200 backend 2>&1 | findstr /C:"ERROR" /C:"401"
```

**Log của các job cron** (đây là nơi duy nhất ghi lại "cron đã chạy gì"):
```cmd
docker exec stock-lakehouse-scheduler tail -50 /app/logs/scheduled_jobs.log
docker exec stock-lakehouse-scheduler tail -50 /app/logs/cron.log
```

---

## 6. Vào bên trong container

```cmd
docker exec -it stock-lakehouse-backend bash
docker exec -it stock-lakehouse-scheduler bash
docker exec -it stock-lakehouse-mysql bash
```

Trong bash của container:
```bash
env | grep MINIO        # xem biến môi trường
cat /app/.env           # xem file env
ls /app                 # xem cấu trúc
cat /etc/cron.d/stock-lakehouse   # xem lịch cron (chỉ có trong container scheduler)
```

---

## 7. Dừng / Xoá containers

**Dừng** (giữ image, dữ liệu giữ nguyên):
```cmd
docker compose --profile all stop
```

**Dừng + xoá container** (dữ liệu trên đĩa vẫn còn):
```cmd
docker compose --profile all down
```

**Xoá hết, kể cả dữ liệu** (cẩn thận!):
```cmd
docker compose --profile all down -v
```

> **Lưu ý về nơi chứa dữ liệu:** dự án dùng **bind mount** (mount thư mục), KHÔNG dùng named volume:
> - MySQL: `/var/lib/docker-data/mysql` → `/var/lib/mysql`
> - MinIO: `/var/lib/docker-data/minio` → `/data`
>
> `/var/lib/docker-data` nằm trên **đĩa ext4 bên trong WSL2** (không phải ổ D: của Windows).
> Xem từ Windows: `\\wsl$\Ubuntu-24.04\var\lib\docker-data\...`
> `docker compose down -v` **không** xóa dữ liệu này. Xóa thật phải `rm -rf` thủ công trên `/var/lib/docker-data` — rất nguy hiểm.

**Tắt nhanh không cần Docker**:
```cmd
powershell -ExecutionPolicy Bypass -File D:\School\kltn\stock-lakehouse-ai\stop-all.ps1
```

---

## 8. Tài nguyên & cleanup

```cmd
docker system df                       REM xem dung lượng image/container/volume
docker system prune -f                 REM xoá rác (containers dừng, network lỗi)
docker system prune -a -f              REM xoá cả image không dùng
docker image prune -f                  REM xoá image dangling lỡ
```

---

## 9. Lỗi thường gặp & cách xử lý

### Lỗi `open //./pipe/dockerDesktopLinuxEngine`

Docker daemon chưa chạy. Chạy `start-docker-daemon.bat` (xem mục 1).

### Lỗi `port is already allocated`

Có container khác (không thuộc project này) đang chiếm port. Xem:
```cmd
netstat -ano | findstr :9000
```
Tắt process đó, hoặc đổi port trong `docker-compose.yml`.

### Lỗi `no space left on device`

```cmd
docker system prune -a -f --volumes
```

### Container restart liên tục (trạng thái `Restarting`)

Xem log để biết lý do:
```cmd
docker logs --tail=50 stock-lakehouse-backend
```

Sửa code / `.env` rồi:
```cmd
docker compose --profile all up -d --build backend scheduler
```

### Backend báo `unhealthy` nhưng log toàn Kafka connection

Image `backend` đang cũ (build từ trước khi gỡ Kafka ngày 10/11/2026). Build lại:
```cmd
docker compose --profile all up -d --build backend scheduler
```

---

## 10. Kiểm tra nhanh hệ thống có chạy đúng

```cmd
REM 1. Daemon sống?
docker info >nul && echo DAEMON OK

REM 2. Containers chạy? (kỳ vọng: mysql, minio, backend, frontend, scheduler)
docker compose --profile all ps

REM 3. Backend reachable?
curl http://localhost:8000/api/v1/health

REM 4. System status (MySQL + MinIO + số dòng từng tầng)
curl http://localhost:8000/api/v1/system/status

REM 5. MySQL reachable?
docker exec stock-lakehouse-mysql mysqladmin ping -h 127.0.0.1 -uroot -p123456

REM 6. MinIO reachable? (MinIO chạy network_mode: host)
curl http://localhost:9000/minio/health/live

REM 7. Scheduler đã nạp lịch cron chưa? (xem file crontab được mount vào container)
docker exec stock-lakehouse-scheduler cat /etc/cron.d/stock-lakehouse

REM 8. Finnhub API key còn hạn?
curl "https://finnhub.io/api/v1/quote?symbol=AAPL&token=YOUR_KEY"
```

---

## 11. Kiểm tra bảng `predictions` (dự báo phiên kế tiếp)

```cmd
REM Đếm tổng số dòng dự báo
docker exec stock-lakehouse-mysql mysql -uroot -p123456 stock_lakehouse -e "SELECT COUNT(*) AS total FROM predictions;"

REM Xem các dòng mới nhất
docker exec stock-lakehouse-mysql mysql -uroot -p123456 stock_lakehouse -e "SELECT symbol, model_name, target_session, reference_close, predicted_close, predicted_return, source, created_at FROM predictions ORDER BY created_at DESC LIMIT 10;"

REM Số mã có dự báo cho phiên mới nhất
docker exec stock-lakehouse-mysql mysql -uroot -p123456 stock_lakehouse -e "SELECT COUNT(DISTINCT symbol) AS symbols FROM predictions WHERE target_session = (SELECT MAX(target_session) FROM predictions);"

REM Danh sách bảng trong database
docker exec stock-lakehouse-mysql mysql -uroot -p123456 stock_lakehouse -e "SHOW TABLES;"
```

> Bảng `predictions` được tạo bởi migration `backend/alembic/versions/0002_predictions.py`.
> Nếu báo lỗi `Table 'stock_lakehouse.predictions' doesn't exist`, chạy:
> ```cmd
> cd backend
> .\.venv\Scripts\python.exe scripts\init_database.py
> ```

---

## 12. Chạy job của scheduler bằng tay (không đợi cron)

```cmd
REM Batch EOD: lấy giá ngày vừa rồi -> dựng lại Silver/Gold -> dự báo phiên tới
docker exec stock-lakehouse-scheduler /opt/venv/bin/python scripts/run_scheduled_job.py eod

REM Luồng tin tức đã bị gỡ ngày 12/11/2026 (độ phủ đo được chỉ 0,00%).
REM Job `news` và `coverage` không còn trong backend/crontab.
```

---

## 13. File đường dẫn nhanh

| File | Mục đích |
|---|---|
| `D:\School\kltn\stock-lakehouse-ai\docker-compose.yml` | Khai báo services |
| `D:\School\kltn\stock-lakehouse-ai\backend\.env` | API keys, config |
| `D:\School\kltn\stock-lakehouse-ai\backend\crontab` | Lịch cron (giờ UTC) của container `scheduler` |
| `D:\School\kltn\stock-lakehouse-ai\backend\scripts\run_scheduled_job.py` | Entrypoint của các job cron |
| `D:\School\kltn\stock-lakehouse-ai\start-docker-daemon.bat` | Khởi động Docker daemon (nhẹ) |
| `D:\School\kltn\stock-lakehouse-ai\start-docker-daemon.ps1` | Phiên bản PowerShell |
| `D:\School\kltn\stock-lakehouse-ai\stop-all.ps1` | Tắt tất cả container |
| `D:\School\kltn\stock-lakehouse-ai\README.md` | Tài liệu dự án |

---

## 14. Lệnh "trong ngày" — chạy thường xuyên

```cmd
REM Mỗi lần khởi động máy
start-docker-daemon.bat
docker compose --profile all up -d

REM Khi sửa code Python
docker compose --profile all up -d --build backend scheduler

REM Khi sửa .env
docker compose --profile all restart backend scheduler

REM Xem log realtime
docker compose --profile all logs -f backend

REM Xem cron đã chạy gì
docker exec stock-lakehouse-scheduler tail -50 /app/logs/scheduled_jobs.log

REM Tắt hết khi đi ngủ
docker compose --profile all stop
taskkill /F /IM dockerd.exe
```
