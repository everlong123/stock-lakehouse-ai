"""Simple inspect test."""
import json
from kafka import KafkaConsumer

consumer = KafkaConsumer(
    "stock-ohlcv-test",
    bootstrap_servers="localhost:9094",
    auto_offset_reset="earliest",
    enable_auto_commit=False,
    consumer_timeout_ms=8000,
    group_id=f"inspector-{__import__('time').time()}",
    api_version=(2, 5, 0),
)
print("Consumer created, polling...")
n = 0
for msg in consumer:
    n += 1
    val = msg.value.decode("utf-8")[:150]
    print(f"  {msg.partition}@{msg.offset}: {val}")
consumer.close()
print(f"Total: {n}")