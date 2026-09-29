# MySQL

Engine: MySQL 8.x  
Driver: `mysql+pymysql://user:password@host:3306/stock_lakehouse`

Tạo database:

```sql
CREATE DATABASE stock_lakehouse
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

Migration:

```bat
cd backend
alembic upgrade head
```

Hoặc:

```bat
python scripts\init_database.py
```

## Tables

### users
id, username, email, password_hash, role (admin|user), created_at, updated_at

Password được băm bằng bcrypt. Không lưu plaintext.

### pipeline_runs
id, pipeline_name, symbol, status, start_time, end_time, records_processed, error_count, message, created_at

### model_runs
id, symbol, model_name, train/validation/test windows, features, parameters, mae, rmse, mape, directional_accuracy, model_path, created_at

### backtest_runs
id, symbol, strategy, start_date, end_date, initial_capital, final_capital, total_return, win_rate, sharpe_ratio, maximum_drawdown, number_of_trades, profit_factor, parameters, created_at

### agent_conversations
id, session_id, user_message, assistant_message, tool_name, tool_arguments, tool_result, created_at

Adminer (nếu dùng Docker): http://localhost:8080
