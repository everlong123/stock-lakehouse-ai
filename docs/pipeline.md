# Pipeline

## Manual Pipeline (Primary)

Pipeline chính của đồ án là batch processing chạy qua các script trong `backend/scripts/`, theo luồng Medallion (Bronze -> Silver -> Gold).

### Luồng:

1. collect_data (yfinance, finnhub, alpha_vantage, ssi_vn, multi_source failover)
2. validate_data (provider-side + silver-side checks)
3. store_bronze (MinIO `stock-bronze/`)
4. transform_silver (cleaning, partition by symbol/year/month)
5. data_quality_check (critical fail -> không build Gold)
6. build_gold (94 technical + macro + regime + candlestick features)

### Chạy local:

```bat
python scripts\ingest_historical.py --years 10
python scripts\run_pipeline.py --symbol ALL
```

### API:

`POST /api/v1/pipeline/run`

```json
{ "symbol": "AAPL", "interval": "1d", "source": "yfinance" }
```

### Quality report:

record_count, duplicate_count, missing_count, invalid_ohlc_count, invalid_volume_count, min_timestamp, max_timestamp, quality_status

### Idempotent: rerun không nhân bản business key `(symbol, timestamp)`.

### Chạy local:

```bat
python scripts\ingest_historical.py --years 10
python scripts\run_pipeline.py --symbol ALL
```

### API:

`POST /api/v1/pipeline/run`

```json
{ "symbol": "AAPL", "interval": "1d", "source": "yfinance" }
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

# Kafka UI: http://localhost:8090
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
