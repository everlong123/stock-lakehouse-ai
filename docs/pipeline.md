# Pipeline

## Manual Pipeline (Primary)

Pipeline chính của đồ án là batch processing chạy qua các script trong `backend/scripts/`, theo luồng Medallion (Bronze -> Silver -> Gold).

### Luồng

1. `collect_data` (yfinance, finnhub, alpha_vantage, ssi_vn, multi_source failover)
2. `validate_data` (provider-side + silver-side checks)
3. `store_bronze` (MinIO `stock-bronze/`)
4. `transform_silver` (cleaning, partition by `symbol/year/month`, engine = Pandas)
5. `data_quality_check` (critical fail -> không build Gold)
6. `build_gold` (94 technical + macro + regime + candlestick features)

### Chạy local

```powershell
# từ thư mục backend/
.venv\Scripts\Activate.ps1

# ingest 10 năm daily OHLCV (Bronze -> Silver -> Gold)
python scripts\ingest_historical.py --source multi_source --years 10

# ingest cổ phiếu VN (SSI iBoard)
python scripts\ingest_vn.py --years 10

# chạy pipeline cho 1 symbol (đã có trong Bronze)
python scripts\run_pipeline.py --symbol VCB
```

### API

`POST /api/v1/pipeline/run`

```json
{
  "symbols": ["VCB"],
  "interval": "1d",
  "source": "multi_source"
}
```

> Schema Pydantic chấp nhận `symbols` (list) chứ không phải `symbol` (string).

### Quality report

`record_count`, `duplicate_count`, `missing_count`, `invalid_ohlc_count`, `invalid_volume_count`, `min_timestamp`, `max_timestamp`, `quality_status`.

### Idempotent

Rerun không nhân bản business key `(symbol, timestamp)`.

---

## Real-time Streaming (Kafka)

Ngoài batch pipeline, project hỗ trợ **near-real-time streaming** với Apache Kafka.

### Architecture

```
Finnhub WebSocket           yfinance polling
        |                          |
        v                          v
+---------------------------------------+
|  StreamPublisher (1s OHLCV aggregation)|
+-----------------+---------------------+
                  |
                  v
            +-----------+
            |   Kafka   |
            |   Topic   |
            | stock-    |
            | ohlcv-raw |
            +-----+-----+
                  |
                  v
+---------------------------------------+
|  Kafka Consumer                       |
+-----------------+---------------------+
                  |
        +---------+---------+
        |                   |
        v                   v
+----------+      +----------------+
| Bronze   |      |  Dashboard     |
| /Silver/ |      |  (live update) |
| Gold     |      +----------------+
+----------+
```

### Setup streaming

```bash
# 1. Đảm bảo Kafka container đang chạy
docker compose up -d kafka

# 2. Tạo topic + buckets
python scripts/bootstrap_infrastructure.py

# 3. Điền FINNHUB_API_KEY vào .env (lấy miễn phí tại https://finnhub.io/)

# 4. Chạy publisher (terminal 1)
python scripts/run_stream_publisher.py --symbols AAPL,MSFT,GOOGL

# 5. Chạy consumer (terminal 2)
python scripts/run_stream_consumer.py --topic stock-ohlcv-raw
```

### Code - Producer

```python
from app.streaming.kafka_producer import StockKafkaProducer, publish_ohlcv

producer = StockKafkaProducer()
producer.send_ohlcv("AAPL", df)

# Hoặc dùng hàm tiện ích
publish_ohlcv("AAPL", df)
```

### Code - Consumer

```python
from app.streaming.kafka_consumer import StockKafkaConsumer

# Chạy consumer nền
consumer = StockKafkaConsumer()
consumer.start()

# Hoặc consume 1 batch
count = consumer.consume_batch(max_records=100)
```

### Topics

| Topic | Mô tả |
|-------|-------|
| `stock-ohlcv-raw` | Raw OHLCV bars từ WebSocket |
| `stock-ohlcv-enriched` | OHLCV + indicators |
| `stock-alerts` | Cảnh báo giá |
| `stock-tick` | Trade tick thô |
| `stock-candle-1m` | Bar 1 phút sau resample |

### Streaming Ingester (Background)

```python
from app.streaming.kafka_producer import StreamingIngester

# Polling liên tục + publish Kafka
ingester = StreamingIngester(
    symbols=["AAPL", "MSFT"],
    interval="1m",
)
ingester.start()  # chạy nền
```

### Enable in `.env`

```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:9094
```

> Bootstrap script `bootstrap_infrastructure.py` tự tạo topic khi Kafka đã healthy. Idempotent - chạy nhiều lần không lỗi.
