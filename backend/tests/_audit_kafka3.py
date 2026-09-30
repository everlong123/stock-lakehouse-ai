"""Test StockKafkaProducer directly."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.streaming.kafka_producer import StockKafkaProducer

print("Initializing StockKafkaProducer (with idempotence=True)...")
start = time.time()
producer = StockKafkaProducer(
    bootstrap_servers="localhost:9094",
    linger_ms=0,
)
print(f"Init took {time.time()-start:.2f}s")

print("Testing send...")
import pandas as pd
df = pd.DataFrame([{
    "symbol": "VCB",
    "timestamp": pd.Timestamp("2026-10-01"),
    "open": 58000.0,
    "high": 58500.0,
    "low": 58000.0,
    "close": 58400.0,
    "volume": 1500000,
}])

try:
    count = producer.send_ohlcv_stream("VCB", df, topic="stock-ohlcv-test-2")
    print(f"Sent {count} messages")
except Exception as e:
    print(f"Failed: {e}")

producer.close()
