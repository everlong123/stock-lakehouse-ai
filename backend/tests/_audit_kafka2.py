"""Test Kafka via docker exec to skip Python kafka client compat issues."""
import subprocess
import json

# Try using kafka-python with shorter timeout
import sys

try:
    from kafka import KafkaProducer, KafkaConsumer
    import kafka as kpkg
    print(f"kafka-python version: {kpkg.__version__}")
except ImportError as e:
    print(f"kafka-python not installed: {e}")
    sys.exit(1)

print("Attempting producer with 5s timeout...")
try:
    producer = KafkaProducer(
        bootstrap_servers="localhost:9094",
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        request_timeout_ms=5000,
        api_version=(2, 0, 0),
    )
    print("Producer connected OK")
    producer.send("stock-ohlcv-test", value={"test": 1}).get(timeout=5)
    print("Message sent OK")
    producer.flush()
    producer.close()
except Exception as e:
    print(f"Producer failed: {type(e).__name__}: {e}")

print("\nAttempting consumer with 5s timeout...")
try:
    consumer = KafkaConsumer(
        "stock-ohlcv-test",
        bootstrap_servers="localhost:9094",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=5000,
        api_version=(2, 0, 0),
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    count = 0
    for msg in consumer:
        count += 1
        print(f"  Got: {msg.value}")
    print(f"Consumer finished ({count} messages)")
    consumer.close()
except Exception as e:
    print(f"Consumer failed: {type(e).__name__}: {e}")
