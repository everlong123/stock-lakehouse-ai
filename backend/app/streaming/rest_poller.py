"""Finnhub REST poller — fetches real 1-minute OHLCV bars from Finnhub HTTP.

This is the fallback / supplement for the Finnhub WebSocket path. When the WS
connection is idle (e.g. outside US market hours, weekend, holidays) we poll
Finnhub's ``/stock/candle`` endpoint at a low rate and republish each bar to
the same Kafka topic the WS path uses.

⚠️  Data-integrity:
- Bars come directly from Finnhub's feed, which aggregates real NYSE/NASDAQ
  trades — these are *real* historical 1-minute candles, NOT random walks.
- Free tier has a 15-minute delay on the candle endpoint; we do NOT add any
  synthetic augmentation.
- Every bar carries ``source = "finnhub_rest"`` so downstream code can
  distinguish it from WS-sourced bars.

Rate limits (Finnhub free tier):
- 60 API calls / minute
- We poll ≤8 symbols every 60 s = 8 req / min, well within budget.

Endpoint used::

    GET https://finnhub.io/api/v1/stock/candle
        ?symbol={SYMBOL}
        &resolution=1            # 1-minute bars
        &from={unix_seconds}     # window start
        &to={unix_seconds}       # window end
        &token={FINNHUB_API_KEY}
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from app.core.config import settings
from app.core.logging_config import get_logger
from app.streaming.kafka_producer import StockKafkaProducer

logger = get_logger(__name__)

FINNHUB_CANDLE_URL = "https://finnhub.io/api/v1/stock/candle"
FINNHUB_TIMEOUT_SECONDS = 15
FREE_TIER_DELAY_SECONDS = 15 * 60  # 15 min delayed data on free tier


class FinnhubRestPoller:
    """Poll Finnhub REST for 1-minute bars and republish to Kafka.

    Use case: keep the lakehouse pipeline producing real data when the
    Finnhub WebSocket is silent (US market closed, weekend, …).
    """

    SOURCE_TAG = "finnhub_rest"
    # We look back further than the polling interval to be sure we don't
    # miss bars due to network hiccups or clock drift.
    LOOKBACK_SECONDS = 300   # 5 minutes per tick
    POLL_INTERVAL = 60       # 1 minute between ticks

    def __init__(
        self,
        symbols: list[str],
        kafka_topic: str,
        bootstrap_servers: str,
        poll_interval_seconds: int = POLL_INTERVAL,
    ) -> None:
        self.symbols = symbols
        self.topic = kafka_topic
        self.poll_interval_seconds = poll_interval_seconds
        self._producer = StockKafkaProducer(bootstrap_servers=bootstrap_servers)
        self._thread: threading.Thread | None = None
        self._running = False
        # Track "last published timestamp per symbol" (UTC, tz-aware) so we
        # never republish the same bar twice.
        self._last_published: dict[str, pd.Timestamp] = {}
        # Reuse one HTTP session (connection pooling)
        self._session = requests.Session()

    # ------------------------------------------------------------ public

    def start(self) -> None:
        if self._running:
            return
        if not settings.finnhub_api_key:
            raise RuntimeError(
                "FINNHUB_API_KEY is required for the REST poller. "
                "Set it in backend/.env."
            )
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="finnhub-rest-poller"
        )
        self._thread.start()
        logger.info(
            "FinnhubRestPoller started: topic=%s symbols=%d every=%ds",
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
        try:
            self._session.close()
        except Exception:  # noqa: BLE001
            pass
        logger.info("FinnhubRestPoller stopped")

    # ------------------------------------------------------------ internals

    def _loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001 - daemon loop must not die
                logger.warning("REST poller tick error: %s", exc)
            # Sleep in 1s slices so stop() is responsive.
            for _ in range(self.poll_interval_seconds):
                if not self._running:
                    return
                time.sleep(1)

    def _tick(self) -> None:
        # Window: now - LOOKBACK_SECONDS .. now - FREE_TIER_DELAY_SECONDS.
        # We use a 5-min window so each symbol yields ~5 fresh bars per tick.
        now = datetime.now(timezone.utc)
        window_end = now - pd.Timedelta(seconds=FREE_TIER_DELAY_SECONDS)
        window_start = window_end - pd.Timedelta(seconds=self.LOOKBACK_SECONDS)

        published = 0
        for symbol in self.symbols:
            try:
                published += self._poll_symbol(symbol, window_start, window_end)
            except Exception as exc:  # noqa: BLE001
                # Don't let one bad symbol kill the loop.
                logger.debug("REST poll failed for %s: %s", symbol, exc)

        if published:
            logger.info(
                "REST poller published %d fresh bar(s) for %d/%d symbol(s)",
                published,
                len(self.symbols),
                len(self.symbols),
            )

    def _poll_symbol(
        self,
        symbol: str,
        window_start: pd.Timestamp,
        window_end: pd.Timestamp,
    ) -> int:
        params = {
            "symbol": symbol,
            "resolution": "1",  # 1-minute bars
            "from": int(window_start.timestamp()),
            "to": int(window_end.timestamp()),
            "token": settings.finnhub_api_key,
        }

        try:
            response = self._session.get(
                FINNHUB_CANDLE_URL,
                params=params,
                timeout=FINNHUB_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            logger.debug("Finnhub HTTP error for %s: %s", symbol, exc)
            return 0
        except ValueError as exc:
            logger.debug("Finnhub JSON parse error for %s: %s", symbol, exc)
            return 0

        # Finnhub returns {"s":"ok", "t":[...], "o":[...], "h":[...], ...}
        # or {"s":"no_data"} if the window is empty (e.g. weekend).
        status = data.get("s")
        if status != "ok":
            return 0

        timestamps = data.get("t") or []
        opens = data.get("o") or []
        highs = data.get("h") or []
        lows = data.get("l") or []
        closes = data.get("c") or []
        volumes = data.get("v") or []

        if not timestamps:
            return 0

        frame = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
                "open": [float(x) for x in opens],
                "high": [float(x) for x in highs],
                "low": [float(x) for x in lows],
                "close": [float(x) for x in closes],
                "adj_close": [float(x) for x in closes],
                "volume": [float(x) for x in volumes],
            }
        )

        # Skip bars we've already published.
        last_ts = self._last_published.get(symbol)
        if last_ts is not None:
            frame = frame[frame["timestamp"] > last_ts]

        if frame.empty:
            return 0

        payload = pd.DataFrame(
            {
                "symbol": symbol.upper(),
                "timestamp": frame["timestamp"],
                "open": frame["open"].astype(float),
                "high": frame["high"].astype(float),
                "low": frame["low"].astype(float),
                "close": frame["close"].astype(float),
                "adj_close": frame["adj_close"].astype(float),
                "volume": frame["volume"].astype(float),
                "source": self.SOURCE_TAG,
                "ingestion_time": datetime.now(timezone.utc),
            }
        )

        try:
            sent = self._producer.send_ohlcv_stream(
                "batch", payload, topic=self.topic
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("REST poller Kafka send failed: %s", exc)
            return 0

        # Update cursor
        self._last_published[symbol] = payload["timestamp"].max()
        return sent
