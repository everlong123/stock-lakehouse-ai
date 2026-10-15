"""VN REST poller — fallback for the SSI iBoard WebSocket publisher.

The SSI iBoard WebSocket is silent outside VN trading hours (09:00-11:30
and 13:00-15:00 ICT, Monday-Friday). To keep the lakehouse pipeline
producing real data the rest of the time we re-use the existing
:class:`SSIVNProvider` and publish its ``get_latest_data`` results to
the same Kafka topic the WebSocket path uses.

⚠️  Data-integrity:
- Every bar comes from the public SSI iBoard REST API - real exchange
  data, not a random walk.
- The same ``*1000`` VND conversion that ``SSIVNProvider._normalize``
  applies is used here, so prices in Bronze are absolute VND.
- Every bar carries ``source = "vn_rest"`` so downstream code can
  distinguish WS-sourced bars from REST-sourced bars.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests

from app.core.config import settings
from app.core.logging_config import get_logger
from app.data_sources.ssi_vn_provider import SSIVNProvider
from app.streaming.kafka_producer import StockKafkaProducer

logger = get_logger(__name__)

#: Poll once per minute. The SSI REST API does not have a published
#: rate-limit; we add a small per-symbol sleep inside the provider.
POLL_INTERVAL = 60


class VNRestPoller:
    """Poll SSI iBoard REST for fresh bars and republish to Kafka.

    The poller keeps a per-symbol "last published timestamp" cursor so
    it never republishes the same bar twice. Outside trading hours
    ``SSIVNProvider.get_latest_data`` returns the same stale bar over
    and over, so the dedup effectively pauses the poller until a new
    bar appears.
    """

    SOURCE_TAG = "vn_rest"
    # How far back to look for fresh bars on each tick. We use a 5-minute
    # window so each tick yields up to 5 fresh 1-minute bars per symbol.
    LOOKBACK_SECONDS = 86400  # 1 day — always cover at least the last session
                               # so the lakehouse gets a bar on the first
                               # tick after a restart.

    def __init__(
        self,
        symbols: list[str],
        kafka_topic: str,
        bootstrap_servers: str,
        poll_interval_seconds: int = POLL_INTERVAL,
    ) -> None:
        self.symbols = [s.upper() for s in symbols]
        self.topic = kafka_topic
        self.poll_interval_seconds = poll_interval_seconds
        self._producer = StockKafkaProducer(bootstrap_servers=bootstrap_servers)
        self._provider = SSIVNProvider(rate_limit_sleep=0.2)
        self._thread: threading.Thread | None = None
        self._running = False
        # Track "last published timestamp per symbol" (UTC, tz-aware).
        self._last_published: dict[str, pd.Timestamp] = {}

    # ──────────────────────────────────────────────────── public

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="vn-rest-poller"
        )
        self._thread.start()
        logger.info(
            "VNRestPoller started: topic=%s symbols=%d every=%ds",
            self.topic,
            len(self.symbols),
            self.poll_interval_seconds,
        )

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        try:
            self._producer.close()
        except Exception:  # noqa: BLE001
            pass
        logger.info("VNRestPoller stopped")

    # ──────────────────────────────────────────────────── internals

    def _loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001
                logger.warning("VN REST poller tick error: %s", exc)
            for _ in range(self.poll_interval_seconds):
                if not self._running:
                    return
                time.sleep(1)

    def _tick(self) -> None:
        end = datetime.now(timezone.utc)
        start = end - timedelta(seconds=self.LOOKBACK_SECONDS)

        published = 0
        for symbol in self.symbols:
            try:
                published += self._poll_symbol(symbol, start, end)
            except Exception as exc:  # noqa: BLE001
                # Don't let one bad symbol kill the loop.
                logger.debug("VN REST poll failed for %s: %s", symbol, exc)

        if published:
            logger.info(
                "VN REST poller published %d fresh bar(s) across %d symbol(s)",
                published,
                len(self.symbols),
            )

    def _poll_symbol(
        self,
        symbol: str,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        try:
            frame = self._provider.get_historical_data(
                symbol=symbol, start=window_start, end=window_end, interval="1m"
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("VN REST historical fetch failed for %s: %s", symbol, exc)
            return 0
        if frame is None or frame.empty:
            return 0

        # Filter to only new rows
        last_ts = self._last_published.get(symbol)
        if last_ts is not None:
            frame = frame[frame["timestamp"] > last_ts]
        if frame.empty:
            return 0

        # Override the provider-set source with our poller tag so we can
        # distinguish REST bars from any future batches the same provider
        # might emit.
        frame = frame.copy()
        frame["source"] = self.SOURCE_TAG
        frame["ingestion_time"] = datetime.now(timezone.utc)

        try:
            sent = self._producer.send_ohlcv_stream(
                "batch", frame, topic=self.topic
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("VN REST Kafka send failed: %s", exc)
            return 0

        self._last_published[symbol] = frame["timestamp"].max()
        return sent
