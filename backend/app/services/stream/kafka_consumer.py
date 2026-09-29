"""
Kafka Consumer - Aggregate tick data to 1-minute candles
Đọc tick từ Kafka, tổng hợp thành candle 1 phút, lưu vào Silver Layer
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from threading import Thread

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CandleAggregator:
    """Tổng hợp tick data thành 1-minute candles"""
    
    def __init__(
        self,
        kafka_bootstrap: str = "localhost:9094",
        input_topic: str = "stock-tick",
        output_topic: str = "stock-candle-1m",
        aggregation_window: int = 60,  # seconds
    ):
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.window = aggregation_window
        
        # Consumer
        self.consumer = KafkaConsumer(
            input_topic,
            bootstrap_servers=kafka_bootstrap,
            group_id="candle-aggregator",
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        
        # Producer - output to Silver Layer
        self.producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
        )
        
        # Buffer: symbol -> list of ticks
        self.buffer: dict[str, list] = defaultdict(list)
        self.window_start: dict[str, datetime] = {}
        
    def _aggregate_candle(self, symbol: str) -> dict:
        """Tạo candle từ buffer"""
        ticks = self.buffer[symbol]
        if not ticks:
            return {}
        
        prices = [t["price"] for t in ticks]
        volumes = [t["volume"] for t in ticks]
        
        # Get window timestamp (truncate to minute)
        now = datetime.now()
        candle_time = now.replace(second=0, microsecond=0)
        
        candle = {
            "symbol": symbol,
            "timestamp": candle_time.isoformat(),
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": sum(volumes),
            "tick_count": len(ticks),
            "source": "SSI",
        }
        
        # Clear buffer
        self.buffer[symbol] = []
        self.window_start[symbol] = now
        
        return candle
    
    def _is_window_complete(self, symbol: str) -> bool:
        """Kiểm tra xem window đã complete chưa"""
        if symbol not in self.window_start:
            return False
        
        elapsed = (datetime.now() - self.window_start[symbol]).total_seconds()
        return elapsed >= self.window
    
    def _should_aggregate(self, symbol: str) -> bool:
        """Quyết định có aggregate cho symbol không"""
        if symbol not in self.buffer or not self.buffer[symbol]:
            return False
        return self._is_window_complete(symbol)
    
    def run(self):
        """Main loop - đọc ticks và aggregate"""
        logger.info(f"Starting candle aggregator (window={self.window}s)")
        logger.info(f"Input: {self.input_topic} -> Output: {self.output_topic}")
        
        try:
            for message in self.consumer:
                tick = message.value
                symbol = tick.get("symbol")
                
                if not symbol:
                    continue
                
                # Initialize window if new symbol
                if symbol not in self.window_start:
                    self.window_start[symbol] = datetime.now()
                
                # Add to buffer
                self.buffer[symbol].append(tick)
                
                # Check if window complete - aggregate
                if self._should_aggregate(symbol):
                    candle = self._aggregate_candle(symbol)
                    if candle:
                        self._send_candle(candle)
                        
        except KeyboardInterrupt:
            logger.info("Shutting down aggregator...")
        finally:
            self._flush_all()
            self.consumer.close()
            self.producer.close()
    
    def _send_candle(self, candle: dict):
        """Gửi candle vào Kafka output topic"""
        try:
            self.producer.send(
                self.output_topic,
                value=candle,
                key=candle["symbol"].encode("utf-8"),
            )
            self.producer.flush()
            logger.debug(f"Candle: {candle['symbol']} @ {candle['timestamp']} close={candle['close']}")
        except KafkaError as e:
            logger.error(f"Failed to send candle: {e}")
    
    def _flush_all(self):
        """Flush remaining candles"""
        for symbol in list(self.buffer.keys()):
            if self.buffer[symbol]:
                candle = self._aggregate_candle(symbol)
                if candle:
                    self._send_candle(candle)


class CandleAggregatorAsync:
    """Async version sử dụng confluent-kafka"""
    
    def __init__(
        self,
        kafka_bootstrap: str = "localhost:9094",
        input_topic: str = "stock-tick",
        output_topic: str = "stock-candle-1m",
    ):
        try:
            from confluent_kafka import Consumer, Producer, KafkaError
            self.use_confluent = True
        except ImportError:
            self.use_confluent = False
        
        self.kafka_bootstrap = kafka_bootstrap
        self.input_topic = input_topic
        self.output_topic = output_topic
        self.buffer: dict[str, list] = defaultdict(list)
        
        if self.use_confluent:
            self._setup_confluent()
        else:
            self._setup_kafka()
    
    def _setup_kafka(self):
        """Setup với kafka-python"""
        self.consumer = KafkaConsumer(
            self.input_topic,
            bootstrap_servers=self.kafka_bootstrap,
            group_id="candle-aggregator",
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
    
    def _setup_confluent(self):
        """Setup với confluent-kafka (hiệu năng tốt hơn)"""
        from confluent_kafka import Consumer, Producer
        
        conf_consumer = {
            "bootstrap.servers": self.kafka_bootstrap,
            "group.id": "candle-aggregator",
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        }
        conf_producer = {
            "bootstrap.servers": self.kafka_bootstrap,
        }
        
        self.consumer = Consumer(conf_consumer)
        self.producer = Producer(conf_producer)
        
        self.consumer.subscribe([self.input_topic])
    
    def run(self):
        """Main loop"""
        logger.info("Starting async candle aggregator")
        
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                
                if self.use_confluent:
                    tick = json.loads(msg.value().decode("utf-8"))
                else:
                    tick = msg.value
                
                self._process_tick(tick)
                
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.consumer.close()
    
    def _process_tick(self, tick: dict):
        """Xử lý tick - tạo candle nếu window complete"""
        symbol = tick.get("symbol")
        if not symbol:
            return
        
        self.buffer[symbol].append(tick)
        
        # Simple: emit candle every 60 ticks hoặc 60 giây
        if len(self.buffer[symbol]) >= 60:
            candle = self._make_candle(symbol)
            if candle:
                self._emit_candle(candle)
    
    def _make_candle(self, symbol: str) -> dict:
        """Tạo candle từ buffer"""
        ticks = self.buffer[symbol]
        if not ticks:
            return {}
        
        prices = [t["price"] for t in ticks]
        now = datetime.now()
        
        candle = {
            "symbol": symbol,
            "timestamp": now.replace(second=0, microsecond=0).isoformat(),
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": sum(t["volume"] for t in ticks),
            "tick_count": len(ticks),
            "source": "SSI",
        }
        
        self.buffer[symbol] = []
        return candle
    
    def _emit_candle(self, candle: dict):
        """Gửi candle ra Kafka"""
        self.producer.produce(
            self.output_topic,
            key=candle["symbol"],
            value=json.dumps(candle),
        )
        self.producer.poll(0)


def run_aggregator():
    """Entry point cho aggregator"""
    aggregator = CandleAggregator(
        kafka_bootstrap="localhost:9094",
        input_topic="stock-tick",
        output_topic="stock-candle-1m",
    )
    aggregator.run()


if __name__ == "__main__":
    run_aggregator()
