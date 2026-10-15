# Streaming & Real-Time Pipeline

This document explains how the **Finnhub WebSocket → Kafka → Lakehouse**
real-time pipeline works in this project.

```
   Finnhub WebSocket            Kafka topic             Kafka Consumer
   (Free tier, 50 syms)         "stock-ohlcv-raw"       (background)
        │                              │                       │
        ▼                              ▼                       ▼
 ┌──────────────────┐         ┌──────────────┐         ┌──────────────┐
 │ FinnhubWebSocket │ ──►───► │  Kafka topic │ ──►───► │ StockKafka-  │
 │      Client      │ 1s bars │  (raw OHLCV) │  JSON   │  Consumer    │
 └──────────────────┘         └──────────────┘         └──────┬───────┘
        ▲                                                         │
        │                                                         ▼
        │                                                ┌──────────────┐
        │   StreamPublisher:                             │ Bronze +     │
        │   per-second aggregation                       │ Silver +     │
        │   + Kafka producer                             │ Gold layers  │
        └─────────────────────────────────────────────── └──────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `app/streaming/finnhub_websocket.py` | Auto-reconnecting WS client with PING and queue. |
| `app/streaming/stream_publisher.py` | Aggregates trades into 1-second OHLCV bars and publishes to Kafka. |
| `app/streaming/kafka_producer.py`  | Underlying Kafka producer + `StreamingIngester`. |
| `app/streaming/kafka_consumer.py`  | Kafka consumer that writes to Bronze → Silver → Gold. |
| `scripts/run_stream_publisher.py`  | CLI to start the publisher. |
| `scripts/run_stream_consumer.py`   | CLI to start the consumer. |
| `scripts/bootstrap_infrastructure.py` | Creates MinIO buckets and Kafka topics. |

## Free tier limits (Finnhub)

- **1** simultaneous WebSocket connection
- **50** subscribed symbols
- **~50** messages / second across all symbols
- Historical OHLCV: 1m/5m/15m lookback ≤ 30 days; 1h ≤ 365 days; daily ≤ 10 years

## Setup

1. Start the infrastructure (MinIO + Kafka via Docker):

   ```bash
   docker compose up -d
   python scripts/bootstrap_infrastructure.py
   ```

2. Set the Finnhub API key in `.env` (free key at https://finnhub.io/):

   ```env
   FINNHUB_API_KEY=your-key-here
   USE_KAFKA=true
   KAFKA_BOOTSTRAP_SERVERS=localhost:9094
   ```

3. (Optional) install the `websocket-client` package:

   ```bash
   pip install -r backend/requirements.txt
   ```

## Smoke test (no Kafka)

```bash
python -m app.streaming.finnhub_websocket --help   # not provided, but you can:
python -c "
from app.streaming.finnhub_websocket import FinnhubWebSocketClient
from app.streaming.stream_publisher import StreamMessage

def cb(m): print('msg:', m.type, m.symbol, len(str(m.payload))[:60])
client = FinnhubWebSocketClient(symbols=['AAPL'], on_message=cb)
client.connect(blocking=False)
import time; time.sleep(10); client.stop()
"
```

## End-to-end Kafka test

```bash
# Terminal 1 - publisher
python scripts/run_stream_publisher.py --symbols AAPL,MSFT --duration 120

# Terminal 2 - consumer (writes to Bronze/Silver/Gold)
python scripts/run_stream_consumer.py --topic stock-ohlcv-raw
```

You can inspect the topic via the Kafka CLI (`kafka-topics.sh --bootstrap-server localhost:9094 --list`) or any Kafka client (kcat, kafkacat, Conduktor).

## In-memory stream cache (Live Stream page)

When `USE_KAFKA=true` the FastAPI lifespan spins up a background Kafka
consumer (`app/services/stream_service.py`) that keeps the last 240 bars per
symbol in a thread-safe cache. The frontend's **Live Stream** page polls
that cache via REST, so the data path is:

```
   producer / publish_bar
            │
            ▼
   topic stock-ohlcv-raw  ──►  StockKafkaConsumer  ──►  StreamCache
                                                         │
                                                         ▼
                                              GET /api/v1/stream/latest
                                              GET /api/v1/stream/history
                                              GET /api/v1/stream/stats
                                              POST /api/v1/stream/ingest
                                                         │
                                                         ▼
                                                  Live Stream page
```

The cache works even when Kafka is disabled. `POST /api/v1/stream/ingest`
records bars directly into the cache (and publishes to Kafka if it is up),
which is how the "Demo ingest" buttons on the Live Stream page drive the
charts without requiring a running broker.