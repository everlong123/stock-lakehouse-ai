# Daily Ingest Setup (GitHub Actions + Ngrok)

Tự động chạy ingest dữ liệu mỗi ngày lúc 18:00 (UTC+7) — tắt máy vẫn chạy.

## Kiến trúc

```
GitHub Actions (cloud, free)
  → chạy script ingest mỗi ngày 11:00 UTC
  → ghi vào MinIO local thông qua ngrok tunnel
  → máy local chỉ cần Docker Desktop + ngrok đang chạy
```

## Bước 1: Cài ngrok (1 lần)

Tải từ https://ngrok.com/download (free) hoặc:

```powershell
choco install ngrok
```

Đăng ký tài khoản miễn phí tại https://dashboard.ngrok.com/signup, lấy authtoken:

```powershell
ngrok config add-authtoken <YOUR_AUTHTOKEN>
```

## Bước 2: Khởi động MinIO + ngrok mỗi lần mở máy

MinIO đã chạy trong Docker (port 9000). Chạy ngrok:

```powershell
ngrok http 9000 --domain=<your-reserved-subdomain>.ngrok-free.app
```

Nếu chưa reserve domain, bỏ `--domain`, ngrok sẽ random URL mỗi lần chạy.

Sao chép URL kiểu `https://xxxx.ngrok-free.app`.

## Bước 3: Cấu hình GitHub Secrets

Vào https://github.com/everlong123/stock-lakehouse-ai/settings/secrets/actions → New repository secret:

| Secret name | Value |
|-------------|-------|
| `MINIO_NGROK_URL` | URL ngrok từ bước 2 (không có path) |
| `MINIO_HOST` | `<id>.ngrok-free.app` (host:port, không có scheme) |
| `MINIO_ACCESS_KEY` | `minioadmin` |
| `MINIO_SECRET_KEY` | `minioadmin123` |

**Lưu ý**: nếu dùng free ngrok không reserve domain, `MINIO_HOST` thay đổi mỗi lần → phải update secret hoặc dùng reserved domain ($5/tháng).

## Bước 4: Test thử

Vào tab Actions → Daily Stock Ingest → Run workflow.

Kiểm tra MinIO local có data mới:

```powershell
# Mở http://localhost:9001 (MinIO Console)
# Login: minioadmin / minioadmin123
# Bucket stock-bronze -> prefix symbol=AAPL/
```

## Bước 5: Auto-start ngrok khi mở máy (Windows)

1. Mở `shell:startup` (Win+R → `shell:startup`)
2. Tạo file `start-ngrok.bat`:

```bat
@echo off
cd C:\path\to\ngrok
ngrok http 9000 --domain=<your-domain>.ngrok-free.app
```

## Giới hạn

- **GitHub Actions free**: 2000 phút/tháng — 1 lần chạy ~5-10 phút × 30 = 300 phút ✅
- **Ngrok free**: 1GB bandwidth/tháng, đủ cho data ingest hằng ngày
- **Cron tối thiểu**: 5 phút/lần (GitHub cho phép)
- **Máy local phải bật** để chạy MinIO + ngrok

## Troubleshooting

- **Lỗi 502/403 từ MinIO**: kiểm tra ngrok còn chạy không
- **AWS4-HMAC error**: đảm bảo `MINIO_SECURE=true` trong env (vì ngrok dùng HTTPS)
- **Connection timeout**: MinIO docker chưa start, chạy `docker start stock-lakehouse-minio`
