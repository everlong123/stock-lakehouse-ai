"""Simple Kafka inspect using manual partition assign (no group)."""
import json
import time
from kafka import KafkaConsumer, TopicPartition

print("Creating consumer (manual assign)...")
consumer = KafkaConsumer(
    bootstrap_servers="localhost:9094",
    auto_offset_reset="earliest",
    enable_auto_commit=False,
    consumer_timeout_ms=5000,
    api_version=(2, 5, 0),
    group_id=None,  # No consumer group
)

# Assign partition 0 of topic manually
tp = TopicPartition("stock-ohlcv-test", 0)
consumer.assign([tp])
consumer.seek_to_beginning(tp)

print("Polling...")
n = 0
start = time.time()
while time.time() - start < 10:
    records = consumer.poll(timeout_ms=1000)
    for tp, messages in records.items():
        for msg in messages:
            n += 1
            val = msg.value.decode("utf-8")[:120]
            print(f"  offset={msg.offset}: {val}")
    if n > 0 and time.time() - start > 3:
        break

consumer.close()
print(f"Total: {n}")