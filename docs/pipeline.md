# Pipeline

## Dagster Orchestration (Primary)

Project sử dụng **Dagster** thay vì manual runner hoặc Airflow:

```
dagster/
├── __init__.py              # Package marker
├── workspace.yaml           # Workspace definition
└── dagster_definitions.py  # Ops, Jobs, Schedules, Assets
```

### Các thành phần chính:

| Component | Mô tả |
|-----------|-------|
| **Ops** | 4 atomic steps: `ingest_bronze`, `transform_silver`, `validate_quality`, `build_gold` |
| **Job** | `stock_lakehouse_job` - compose 4 ops thành pipeline |
| **Schedules** | `daily_lakehouse_pipeline` (6 PM ET, weekdays), `hourly_bronze_refresh` |
| **Assets** | Declarative data outputs với lineage tracking |

### Chạy với Docker:

```bash
docker compose up -d dagster-webserver dagster-daemon postgres

# UI: http://localhost:3000
```

### Chạy local (development):

```bash
# Cài đặt dagster
pip install dagster==1.9.2 dagster-graphql==1.9.2

# Chạy webserver
dagster dev -m dagster.dagster_definitions -p 3000
# Hoặc
DAGSTER_BACKEND_PATH=$(pwd)/backend dagster dev -m dagster.dagster_definitions -p 3000
```

### Manual trigger via API:

```bash
curl -X POST http://localhost:3000/api/v1/lakehouse/run
```

### Tại sao Dagster thay vì Airflow?

| Tiêu chí | Airflow | Dagster |
|----------|---------|---------|
| DAG authoring | YAML + Python | Pure Python |
| Data awareness | Limited | Native (assets, lineage) |
| Testing | Harder | dagster-test utilities |
| UI | Good | Modern asset graph |
| Learning curve | Higher | Lower (Python-first) |

---

## Manual Pipeline (Fallback)

### Luồng:

1. collect_data
2. validate_data
3. store_bronze
4. transform_silver
5. data_quality_check (critical fail → không build Gold)
6. build_gold

### Chạy local:

```bat
python scripts\generate_sample_data.py
python scripts\run_pipeline.py --symbol ALL
```

### API:

`POST /api/v1/pipeline/run`

```json
{ "symbol": "AAPL", "interval": "1d", "source": "sample" }
```

### Quality report:

record_count, duplicate_count, missing_count, invalid_ohlc_count, invalid_volume_count, min_timestamp, max_timestamp, quality_status

### Idempotent: rerun không nhân bản business key `(symbol, timestamp)`.

---

## Real-time Streaming (Kafka)

Ngoài batch pipeline, project hỗ trợ **real-time streaming** với Apache Kafka.

### Architecture

```
Data Source (yfinance/web)
        │
        ▼
┌─────────────────┐
│  Kafka Producer │
│  (publisher)    │
└────────┬────────┘
         │
    ┌────▼────┐
    │  Kafka  │
    │  Topic  │
    │ stock-  │
    │ ohlcv-  │
    │ raw     │
    └────┬────┘
         │
         ▼
┌─────────────────┐
│  Kafka Consumer │
│  (real-time)    │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
Bronze     Dashboard
 Storage   (live)
```

### Start Kafka

```bash
docker compose up -d kafka kafka-ui

# Kafka UI: http://localhost:8080
# Kafka port:  localhost:9094
```

### Code - Producer

```python
from app.streaming.kafka_producer import StockKafkaProducer, publish_ohlcv

# Publish OHLCV data to Kafka
producer = StockKafkaProducer()
producer.send_ohlcv("AAPL", df)

# Or convenience function
publish_ohlcv("AAPL", df)
```

### Code - Consumer

```python
from app.streaming.kafka_consumer import StockKafkaConsumer

# Start consuming in background
consumer = StockKafkaConsumer()
consumer.start()

# Or consume batch manually
count = consumer.consume_batch(max_records=100)
```

### Topics

| Topic | Description |
|-------|-------------|
| `stock-ohlcv-raw` | Raw OHLCV bars |
| `stock-ohlcv-enriched` | Enriched with indicators |
| `stock-alerts` | Price alerts |

### Streaming Ingester (Background)

```python
from app.streaming.kafka_producer import StreamingIngester

# Continuous polling and publishing
ingester = StreamingIngester(
    symbols=["AAPL", "MSFT"],
    interval="1m",
)
ingester.start()  # Runs in background
```

### Enable in .env

```bash
use_kafka=true
kafka_bootstrap_servers=localhost:9094
```
