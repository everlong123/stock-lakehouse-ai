"""End-to-end streaming test using StockKafkaProducer/Consumer."""
import sys
import json
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

print("=" * 70)
print("END-TO-END STREAMING TEST (using StockKafkaProducer/Consumer)")
print("=" * 70)

# 1. Start consumer in background
from app.streaming.kafka_consumer import StockKafkaConsumer

print("\n[1] Starting consumer in background thread...")
consumer = StockKafkaConsumer(
    group_id=f"audit-e2e-{int(time.time())}",
    topics=["stock-ohlcv-audit-test"],
    bootstrap_servers="localhost:9094",
    poll_timeout_ms=500,
)
consumer.start()
time.sleep(2)
print(f"   Consumer started")

# 2. Produce 5 messages
print("\n[2] Producing 5 test messages via StockKafkaProducer...")
from app.streaming.kafka_producer import StockKafkaProducer
import pandas as pd

producer = StockKafkaProducer(
    bootstrap_servers="localhost:9094",
    linger_ms=0,
)

# Use single-bar send_ohlcv (compatible with consumer)
for i in range(5):
    df = pd.DataFrame([{
        "symbol": "VCB",
        "timestamp": pd.Timestamp(f"2026-10-01T10:0{i}:00+00:00"),
        "open": 58300.0 + i * 10,
        "high": 58500.0 + i * 10,
        "low": 58000.0 + i * 10,
        "close": 58400.0 + i * 10,
        "adj_close": 58400.0 + i * 10,
        "volume": 1500000 + i * 1000,
        "source": "audit_test",
    }])
    sent = producer.send_ohlcv("VCB", df, topic="stock-ohlcv-audit-test")
    print(f"   Bar {i+1}: sent {sent} message")

producer.close()

# 3. Wait for consumer to process
print("\n[3] Waiting for consumer to process (max 10s)...")
for _ in range(20):
    time.sleep(0.5)
    # Check bronze layer for new audit_test records
    from app.lakehouse import BronzeLayer
    bronze = BronzeLayer()
    df_bronze = bronze.storage.read_prefix("bronze", "")
    if not df_bronze.empty and "source" in df_bronze.columns:
        audit_records = df_bronze[df_bronze["source"] == "audit_test"]
        if len(audit_records) >= 5:
            print(f"   Found {len(audit_records)} audit_test records in Bronze layer")
            break

# 4. Stop
consumer.stop()
print("\n[4] Consumer stopped")

# 5. Final verification
print("\n[5] Final Bronze check...")
from app.lakehouse import BronzeLayer
bronze = BronzeLayer()
df_bronze = bronze.storage.read_prefix("bronze", "")
if not df_bronze.empty and "source" in df_bronze.columns:
    audit = df_bronze[df_bronze["source"] == "audit_test"]
    print(f"   audit_test records: {len(audit)}")
    if not audit.empty:
        print(f"   Symbols: {sorted(audit['symbol'].unique().tolist())}")
        print(f"   Timestamp range: {audit['timestamp'].min()} -> {audit['timestamp'].max()}")

print("\n" + "=" * 70)
print("E2E STREAMING TEST COMPLETE")
print("=" * 70)