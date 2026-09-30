# Lakehouse System Health Report

**Generated:** 2026-09-30T19:00:47.265344+00:00

## Summary

| Pass | Warn | Fail | Total |
|------|------|------|-------|
| 28 | 0 | 0 | 28 |

## Detailed Checks

| Category | Status | Detail |
|----------|--------|--------|
| `Storage backend` | ✅ PASS | backend=minio class=MinioStorageBackend |
| `Storage health` | ✅ PASS | {'backend': 'minio', 'available': True} |
| `Bronze layer` | ✅ PASS | symbols=108 rows=219958 columns=12 |
| `Silver layer` | ✅ PASS | symbols=108 rows=193508 columns=37 |
| `Gold layer` | ✅ PASS | symbols=108 rows=192618 columns=94 |
| `Provider yfinance` | ✅ PASS | class=YFinancePythonProvider source_name=yfinance_python |
| `Provider ssi_vn` | ✅ PASS | class=SSIVNProvider source_name=ssi_vn |
| `Provider multi_source` | ✅ PASS | class=MultiSourceProvider source_name=multi_source |
| `Indicator service` | ✅ PASS | VCB enriched with 24 cols |
| `Forecasting (LR)` | ✅ PASS | MAE=0.00 RMSE=0.00 MAPE=0.00% |
| `Backtesting (MA)` | ✅ PASS | trades=3 return=-20.50% sharpe=-0.391 |
| `GET /api/v1/health` | ✅ PASS | 200 keys=['status', 'app'] |
| `GET /api/v1/stocks/symbols` | ✅ PASS | 200 keys=['symbols'] |
| `GET /api/v1/stocks/VCB?interval=1d` | ✅ PASS | 200 keys=['symbol', 'interval', 'latest'] |
| `GET /api/v1/stocks/FPT/latest?interval=1d` | ✅ PASS | 200 keys=['symbol', 'timestamp', 'open'] |
| `GET /api/v1/stocks/VCB/indicators` | ✅ PASS | 200 keys=['symbol', 'latest', 'summary'] |
| `GET /api/v1/data/stocks/supported` | ✅ PASS | 200 keys=['symbols', 'count'] |
| `POST /api/v1/backtests/run` | ✅ PASS | 200 keys=['symbol', 'strategy', 'start_date'] |
| `POST /api/v1/forecast/train` | ✅ PASS | 200 keys=['symbol', 'model_name', 'train_start'] |
| `POST /api/v1/forecast/predict` | ✅ PASS | 200 keys=['symbol', 'model_name', 'horizon'] |
| `Kafka producer` | ✅ PASS | sent 1 message(s) |
| `Kafka consumer (inspect)` | ✅ PASS | received 1 messages |
| `TCP MinIO API` | ✅ PASS | localhost:9000 |
| `TCP MinIO Console` | ✅ PASS | localhost:9001 |
| `TCP Kafka internal` | ✅ PASS | localhost:9092 |
| `TCP Kafka external` | ✅ PASS | localhost:9094 |
| `TCP Kafka UI` | ✅ PASS | localhost:8090 |
| `Docker containers` | ✅ PASS | 8 stock-lakehouse containers running |

## Coverage

### Backtesting

- ✅ **Backtesting (MA)** — trades=3 return=-20.50% sharpe=-0.391

### Bronze

- ✅ **Bronze layer** — symbols=108 rows=219958 columns=12

### Docker

- ✅ **Docker containers** — 8 stock-lakehouse containers running

### Forecasting

- ✅ **Forecasting (LR)** — MAE=0.00 RMSE=0.00 MAPE=0.00%

### GET

- ✅ **GET /api/v1/health** — 200 keys=['status', 'app']
- ✅ **GET /api/v1/stocks/symbols** — 200 keys=['symbols']
- ✅ **GET /api/v1/stocks/VCB?interval=1d** — 200 keys=['symbol', 'interval', 'latest']
- ✅ **GET /api/v1/stocks/FPT/latest?interval=1d** — 200 keys=['symbol', 'timestamp', 'open']
- ✅ **GET /api/v1/stocks/VCB/indicators** — 200 keys=['symbol', 'latest', 'summary']
- ✅ **GET /api/v1/data/stocks/supported** — 200 keys=['symbols', 'count']

### Gold

- ✅ **Gold layer** — symbols=108 rows=192618 columns=94

### Indicator

- ✅ **Indicator service** — VCB enriched with 24 cols

### Kafka

- ✅ **Kafka producer** — sent 1 message(s)
- ✅ **Kafka consumer (inspect)** — received 1 messages

### POST

- ✅ **POST /api/v1/backtests/run** — 200 keys=['symbol', 'strategy', 'start_date']
- ✅ **POST /api/v1/forecast/train** — 200 keys=['symbol', 'model_name', 'train_start']
- ✅ **POST /api/v1/forecast/predict** — 200 keys=['symbol', 'model_name', 'horizon']

### Provider

- ✅ **Provider yfinance** — class=YFinancePythonProvider source_name=yfinance_python
- ✅ **Provider ssi_vn** — class=SSIVNProvider source_name=ssi_vn
- ✅ **Provider multi_source** — class=MultiSourceProvider source_name=multi_source

### Silver

- ✅ **Silver layer** — symbols=108 rows=193508 columns=37

### Storage

- ✅ **Storage backend** — backend=minio class=MinioStorageBackend
- ✅ **Storage health** — {'backend': 'minio', 'available': True}

### TCP

- ✅ **TCP MinIO API** — localhost:9000
- ✅ **TCP MinIO Console** — localhost:9001
- ✅ **TCP Kafka internal** — localhost:9092
- ✅ **TCP Kafka external** — localhost:9094
- ✅ **TCP Kafka UI** — localhost:8090

---

Re-run with: `python backend/tests/_system_audit.py`
