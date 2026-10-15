# Docker Cheatsheet (Windows CMD)

Tài liệu tham chiếu nhanh để chạy project `stock-lakehouse-ai` trên Windows bằng CMD.
Mọi lệnh đều chạy trong **CMD as Administrator** (trừ những lệnh được đánh dấu `[user]`).

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

> Lần đầu build image mất 5-15 phút. Lần sau (đã có image) mất 5-30 giây.

**Chỉ chạy 1 container** (không build lại):
```cmd
docker compose --profile all up -d stream-publisher
```

---

## 3. Restart container (sau khi sửa `.env` hoặc code)

**Restart nhẹ** (giữ image, không build lại — nhanh nhất):
```cmd
docker compose --profile all restart stream-publisher
docker compose --profile all restart backend
```

**Restart + rebuild** (khi sửa code Python):
```cmd
docker compose --profile all up -d --build stream-publisher
```

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
docker compose --profile all logs --tail=100 stream-publisher

REM Follow logs realtime (Ctrl+C để dừng)
docker compose --profile all logs -f stream-publisher

REM Nhiều container cùng lúc
docker compose --profile all logs -f --tail=50 stream-publisher backend

REM Lọc theo keyword (vd: lỗi)
docker compose --profile all logs --tail=200 stream-publisher 2>&1 | findstr /C:"ERROR" /C:"401"
```

---

## 6. Vào bên trong container

```cmd
docker exec -it stock-lakehouse-stream-publisher bash
docker exec -it stock-lakehouse-backend bash
docker exec -it stock-lakehouse-kafka bash
```

Trong bash của container:
```bash
env | grep FINNHUB        # xem biến môi trường
cat /app/.env             # xem file env
ls /app                   # xem cấu trúc
```

---

## 7. Dừng / Xoá containers

**Dừng** (giữ image, dữ liệu giữ nguyên):
```cmd
docker compose --profile all stop
```

**Dừng + xoá container** (nhưng giữ volumes/dữ liệu):
```cmd
docker compose --profile all down
```

**Xoá hết, kể cả dữ liệu** (cẩn thận!):
```cmd
docker compose --profile all down -v
```

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
docker volume prune -f                 REM CẨN THẬN: xoá volumes không dùng
docker image prune -f                      REM xoá image dangling lỡ
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
docker logs --tail=50 stock-lakehouse-stream-publisher
```

Sửa code / `.env` rồi:
```cmd
docker compose --profile all up -d --build stream-publisher
```

---

## 10. Kiểm tra nhanh hệ thống có chạy đúng

```cmd
REM 1. Daemon sống?
docker info >nul && echo DAEMON OK

REM 2. Containers chạy?
docker compose --profile all ps

REM 3. Backend reachable?
curl http://localhost:8080/health

REM 4. Kafka reachable?
docker exec stock-lakehouse-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list

REM 5. Finnhub API key còn hạn?
curl "https://finnhub.io/api/v1/quote?symbol=AAPL&token=YOUR_KEY"
```

Nếu tất cả OK mà stream-publisher vẫn báo `401 Unauthorized` → key trong `.env` sai hoặc bị revoke → tạo key mới trên https://finnhub.io/dashboard.

---

## 11. File đường dẫn nhanh

| File | Mục đích |
|---|---|
| `D:\School\kltn\stock-lakehouse-ai\docker-compose.yml` | Khai báo services |
| `D:\School\kltn\stock-lakehouse-ai\backend\.env` | API keys, config |
| `D:\School\kltn\stock-lakehouse-ai\start-docker-daemon.bat` | Khởi động Docker daemon (nhẹ) |
| `D:\School\kltn\stock-lakehouse-ai\start-docker-daemon.ps1` | Phiên bản PowerShell |
| `D:\School\kltn\stock-lakehouse-ai\stop-all.ps1` | Tắt tất cả container |
| `D:\School\kltn\stock-lakehouse-ai\README.md` | Tài liệu dự án |

---

## 12. Lệnh "trong ngày" — chạy thường xuyên

```cmd
REM Mỗi lần khởi động máy
start-docker-daemon.bat
docker compose --profile all up -d

REM Khi sửa code Python
docker compose --profile all up -d --build stream-publisher

REM Khi sửa .env
docker compose --profile all restart stream-publisher backend

REM Xem log realtime
docker compose --profile all logs -f stream-publisher

REM Tắt hết khi đi ngủ
docker compose --profile all stop
taskkill /F /IM dockerd.exe
```