"""Test Kafka producer/consumer with a simple roundtrip."""
import sys
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kafka import KafkaProducer, KafkaConsumer

# Test 1: Connect to Kafka and produce/consume
print("=" * 70)
print("KAFKA ROUNDTRIP TEST")
print("=" * 70)

bootstrap = "localhost:9094"
topic = "stock-ohlcv-test"

# Produce
print(f"\n[1] Producing to {topic}...")
producer = KafkaProducer(
    bootstrap_servers=bootstrap,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)
test_messages = [
    {"symbol": "VCB", "close": 58000.0, "ts": "2026-10-01"},
    {"symbol": "FPT", "close": 63000.0, "ts": "2026-10-01"},
    {"symbol": "HPG", "close": 20150.0, "ts": "2026-10-01"},
]
for msg in test_messages:
    future = producer.send(topic, value=msg)
    future.get(timeout=10)
producer.flush()
producer.close()
print(f"   Produced {len(test_messages)} messages OK")

# Consume
print(f"\n[2] Consuming from {topic}...")
consumer = KafkaConsumer(
    topic,
    bootstrap_servers=bootstrap,
    auto_offset_reset="earliest",
    enable_auto_commit=True,
    group_id=f"audit-test-{time.time()}",
    consumer_timeout_ms=10000,
    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
)

received = []
for msg in consumer:
    received.append(msg.value)
    print(f"   Got: {msg.value}")
    if len(received) >= len(test_messages):
        break
consumer.close()

print(f"\n[3] Consumed {len(received)}/{len(test_messages)} messages")
if received == test_messages:
    print("   PASS: All messages match")
else:
    print(f"   FAIL: Expected {len(test_messages)}, got {len(received)}")
