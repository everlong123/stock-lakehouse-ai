"""Streaming module - Kafka real-time data ingestion and processing."""

from app.streaming.kafka_producer import (
    DEFAULT_BOOTSTRAP_SERVERS,
    StockKafkaProducer,
    StreamingIngester,
    TOPIC_ALERTS,
    TOPIC_OHLCV_ENRICHED,
    TOPIC_OHLCV_RAW,
    get_kafka_producer,
    publish_alert,
    publish_ohlcv,
)
from app.streaming.kafka_consumer import (
    DEFAULT_GROUP_ID,
    RealTimeAggregator,
    StockKafkaConsumer,
    get_kafka_consumer,
    start_consumer,
)
from app.streaming.finnhub_websocket import (
    FINNHUB_WS_URL,
    FinnhubWebSocketClient,
    StreamMessage,
    build_default_client,
)
from app.streaming.stream_publisher import StreamPublisher

__all__ = [
    # Producer
    "StockKafkaProducer",
    "StreamingIngester",
    "get_kafka_producer",
    "publish_ohlcv",
    "publish_alert",
    "TOPIC_OHLCV_RAW",
    "TOPIC_OHLCV_ENRICHED",
    "TOPIC_ALERTS",
    "DEFAULT_BOOTSTRAP_SERVERS",
    # Consumer
    "StockKafkaConsumer",
    "RealTimeAggregator",
    "get_kafka_consumer",
    "start_consumer",
    "DEFAULT_GROUP_ID",
    # WebSocket → Kafka
    "FinnhubWebSocketClient",
    "StreamMessage",
    "StreamPublisher",
    "build_default_client",
    "FINNHUB_WS_URL",
]