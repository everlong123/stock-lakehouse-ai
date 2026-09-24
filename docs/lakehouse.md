# Lakehouse

## Table Format

### Apache Iceberg (Primary - Modern)

Project hỗ trợ **Apache Iceberg** thay vì raw Parquet:

```
use_iceberg=true
ICEBERG_CATALOG_URI=http://localhost:8181
```

**Lợi ích so với raw Parquet:**

| Tính năng | Raw Parquet | Apache Iceberg |
|------------|-------------|----------------|
| Time travel | ❌ | ✅ Query historical versions |
| Schema evolution | ⚠️ Manual | ✅ Safe, atomic |
| ACID writes | ❌ Partial | ✅ Full atomicity |
| Partition pruning | Manual filter | ✅ Automatic hidden partitions |
| Concurrent writes | ❌ Lock issues | ✅ Snapshot isolation |
| Metadata tracking | `_lineage.json` | ✅ Built-in history |

**Containers:**
```bash
docker compose up -d iceberg-rest  # REST API at http://localhost:8181
```

**Code:**
```python
from app.lakehouse.iceberg_manager import get_iceberg_manager

manager = get_iceberg_manager()
manager.create_all_tables()

# Write data
manager.write_bronze(df, symbol="AAPL")

# Time travel - read data from 3 days ago
df_old = manager.read_bronze(symbol="AAPL", as_of_timestamp="3d")
```

### Apache Parquet (Fallback)

```
use_iceberg=false  # Default
```

```
data/bronze/symbol=AAPL/year=2026/month=09/part-001.parquet
```

## Bronze schema

symbol, timestamp, open, high, low, close, adj_close, volume, source, ingestion_time

Hỗ trợ append, schema validation, duplicate checking, lineage (`_lineage.json`).

## Silver rules

- high >= open và high >= close
- low <= open và low <= close
- high >= low
- volume >= 0
- Business key: symbol + timestamp
- Timezone: UTC

Record lỗi: log, count, ghi `silver/_errors/`.

## Gold features

return, log_return, price_change, volume_change  
SMA_5/10/20/50, EMA_12/26, RSI_14  
MACD, MACD_SIGNAL, MACD_HIST  
BB_MIDDLE/UPPER/LOWER  
rolling_std_20, rolling_min_20, rolling_max_20, volume_ma_20  
close_lag_1/2, return_lag_1, volume_lag_1  

Targets (shift -1):

- target_close_next
- target_return_next
- target_direction_next

Storage abstraction: `StorageBackend` → `LocalStorageBackend` | `MinioStorageBackend`.

## Iceberg Tables

### Bronze Table
- **Table:** `lakehouse.bronze_ohlcv`
- **Partition:** `symbol` (identity), `timestamp` (month)
- **Schema:** Raw OHLCV with lineage

### Silver Table
- **Table:** `lakehouse.silver_ohlcv`
- **Partition:** `symbol` (identity), `timestamp` (month)
- **Schema:** Cleaned OHLCV with quality status

### Gold Table
- **Table:** `lakehouse.gold_features`
- **Partition:** `symbol` (identity), `timestamp` (month)
- **Schema:** Features + technical indicators + ML targets
