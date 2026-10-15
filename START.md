# Quick Start

> 📖 **Đọc `LOCAL_DEV.md` trước** — nó là source of truth cho mọi thứ liên quan đến
> setup, troubleshooting, và quyết định local vs Docker.

## 1 lệnh để chạy local

```powershell
# Từ D:\School\kltn\stock-lakehouse-ai
.\start-all.bat
```

2 cửa sổ cmd bật lên (backend :8000 + frontend :5173).

Mở: **http://127.0.0.1:5173**

Tắt: `.\stop-all.bat`

## Khi nào dùng Docker

Code đã ổn định (≥ 1 ngày không regress) thì mới chạy Docker. Xem
`LOCAL_DEV.md` mục "Từ local sang Docker" để biết chi tiết.
