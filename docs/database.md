# MySQL

Engine: MySQL 8.x
Driver: `mysql+pymysql://user:password@host:3307/stock_lakehouse`

MySQL container chạy ở port `3307` (mapped từ 3306 trong container). MySQL chỉ lưu **metadata** của hệ thống - toàn bộ OHLCV lịch sử nằm trong Lakehouse (Parquet trên MinIO).

## Tạo database + chạy migration

```powershell
cd backend
.\.venv\Scripts\Activate.ps1

# Cách 1: dùng helper script (tự tạo DB nếu chưa có + chạy Alembic)
python scripts\init_database.py

# Cách 2: chạy Alembic trực tiếp (DB phải tồn tại sẵn)
alembic upgrade head
```

`scripts/init_database.py` là idempotent - chạy nhiều lần không lỗi. Nếu DB chưa tồn tại, tự tạo; nếu Alembic lỗi, fallback `Base.metadata.create_all()` rồi stamp head.

## Kết nối DB

```bash
# Qua MySQL CLI (host là localhost, port 3307)
mysql -h 127.0.0.1 -P 3307 -u root -p123456

# Hoặc dùng bất kỳ MySQL client nào (DBeaver, TablePlus, MySQL Workbench, ...)
# host: localhost
# port: 3307
# user: root
# password: 123456
# database: stock_lakehouse
```

## Tables

### `users`

| Column | Type | Mô tả |
|--------|------|-------|
| `id` | int PK | |
| `username` | varchar(64) unique | |
| `email` | varchar(120) unique | |
| `password_hash` | varchar(255) | bcrypt hash, không lưu plaintext |
| `role` | enum('admin','user') | |
| `created_at`, `updated_at` | datetime | |

### `pipeline_runs`

| Column | Type | Mô tả |
|--------|------|-------|
| `id` | int PK | |
| `pipeline_name` | varchar(64) | "ingest", "silver_transform", "gold_build" |
| `symbol` | varchar(16) nullable | null nếu pipeline chạy cho nhiều symbol |
| `status` | enum('running','success','failed') | |
| `start_time`, `end_time` | datetime | |
| `records_processed` | int | |
| `error_count` | int | |
| `message` | text | stack trace nếu failed |
| `created_at` | datetime | |

### `model_runs`

| Column | Type | Mô tả |
|--------|------|-------|
| `id` | int PK | |
| `symbol` | varchar(16) | |
| `model_name` | enum('linear_regression','arima','lstm') | |
| `train_start`, `train_end`, `validation_start`, `validation_end`, `test_start`, `test_end` | date | window chia theo thời gian |
| `features` | json | danh sách feature names |
| `parameters` | json | hyperparams (LSTM hidden size, ARIMA order, ...) |
| `mae`, `rmse`, `mape`, `directional_accuracy` | float | metrics trên test set |
| `model_path` | varchar(255) | đường dẫn file model artifact |
| `created_at` | datetime | |

### `backtest_runs`

| Column | Type | Mô tả |
|--------|------|-------|
| `id` | int PK | |
| `symbol` | varchar(16) | |
| `strategy` | enum('ma_crossover','rsi_strategy') | |
| `start_date`, `end_date` | date | |
| `initial_capital`, `final_capital` | float | |
| `total_return` | float | phần trăm |
| `win_rate` | float | |
| `sharpe_ratio`, `maximum_drawdown` | float | |
| `number_of_trades` | int | |
| `profit_factor` | float | |
| `parameters` | json | MA windows, RSI thresholds, ... |
| `created_at` | datetime | |

### `agent_conversations`

| Column | Type | Mô tả |
|--------|------|-------|
| `id` | int PK | |
| `session_id` | varchar(64) index | UUID session |
| `user_message` | text | |
| `assistant_message` | text | |
| `tool_name` | varchar(64) nullable | tool đã gọi (nếu có) |
| `tool_arguments` | json nullable | |
| `tool_result` | json nullable | |
| `created_at` | datetime | |

## Reset database

```powershell
cd backend
# Drop tất cả tables (cẩn thận!)
python scripts\seed_database.py --reset

# Hoặc dùng MySQL CLI
mysql -h 127.0.0.1 -P 3307 -u root -p123456 -e "DROP DATABASE stock_lakehouse; CREATE DATABASE stock_lakehouse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
python scripts\init_database.py
```
