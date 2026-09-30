"""Test full pipeline using batch API but with manual consumer assign."""
import sys
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.streaming.kafka_consumer import StockKafkaConsumer
from app.streaming.kafka_producer import StockKafkaProducer
import pandas as pd

print("=" * 70)
print("END-TO-END STREAMING (manual assign to bypass group rebalance)")
print("=" * 70)

# 1. Start consumer in background - it uses consumer group, will join
print("\n[1] Starting consumer...")
consumer = StockKafkaConsumer(
    group_id=f"audit-{int(time.time())}",
    topics=["stock-ohlcv-e2e"],
    bootstrap_servers="localhost:9094",
    poll_timeout_ms=500,
)

# Monkey-patch to use manual assign instead of subscribe
from kafka import TopicPartition, KafkaConsumer
import threading

def manual_start():
    if consumer._running:
        return
    consumer._running = True
    consumer._thread = None  # No thread

    # Create a fresh consumer with manual assign (no group)
    fresh = KafkaConsumer(
        bootstrap_servers="localhost:9094",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        api_version=(2, 5, 0),
        group_id=None,
        value_deserializer=lambda v: v,
    )
    parts = fresh.partitions_for_topic("stock-ohlcv-e2e") or {0}
    tps = [TopicPartition("stock-ohlcv-e2e", p) for p in parts]
    fresh.assign(tps)
    for tp in tps:
        fresh.seek_to_beginning(tp)
    print(f"   Assigned partitions: {[tp.partition for tp in tps]}")

    # Replace consumer with manual one
    consumer._consumer = fresh

    # Poll loop
    def loop():
        while consumer._running:
            try:
                records = consumer.consumer.poll(timeout_ms=500)
                for tp, messages in records.items():
                    for msg in messages:
                        consumer._process_message(msg)
            except Exception as e:
                print(f"   Loop error: {e}")
                time.sleep(1)
    consumer._thread = threading.Thread(target=loop, daemon=True)
    consumer._thread.start()
    print(f"   Consumer started")

manual_start()
time.sleep(2)

# 2. Produce messages
print("\n[2] Producing 3 messages...")
producer = StockKafkaProducer(
    bootstrap_servers="localhost:9094",
    linger_ms=0,
)

for i in range(3):
    df = pd.DataFrame([{
        "symbol": "FPT",
        "timestamp": pd.Timestamp(f"2026-10-02T10:0{i}:00+00:00"),
        "open": 63000.0 + i * 50,
        "high": 63500.0 + i * 50,
        "low": 62800.0 + i * 50,
        "close": 63200.0 + i * 50,
        "adj_close": 63200.0 + i * 50,
        "volume": 1000000 + i * 1000,
        "source": "e2e_audit",
    }])
    sent = producer.send_ohlcv("FPT", df, topic="stock-ohlcv-e2e")
    print(f"   Bar {i+1}: {sent} sent")

producer.close()

# 3. Wait for processing
print("\n[3] Waiting for consumer to process (max 15s)...")
time.sleep(15)

# 4. Verify in bronze
print("\n[4] Checking Bronze...")
from app.lakehouse import BronzeLayer
bronze = BronzeLayer()
df = bronze.storage.read_prefix("bronze", "")
if not df.empty and "source" in df.columns:
    e2e = df[df["source"] == "e2e_audit"]
    print(f"   e2e_audit records in Bronze: {len(e2e)}")
    if not e2e.empty:
        print(f"   Symbols: {sorted(e2e['symbol'].unique().tolist())}")
        print(f"   Date range: {e2e['timestamp'].min()} -> {e2e['timestamp'].max()}")
else:
    print(f"   No bronze data or source column missing")

# 5. Stop
consumer.stop()
print("\n" + "=" * 70)
print("DONE")
print("=" * 70)