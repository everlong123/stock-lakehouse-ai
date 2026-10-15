"""YFinance EOD poller — fetch 1-day US OHLCV bars and publish to Kafka.

This module replaces :class:`FinnhubRestPoller`, which used Finnhub's
``/stock/candle`` endpoint that was removed from the free tier in
April 2025 (see https://github.com/finnhubio/Finnhub-API/issues/546).

Why yfinance:
- Free, no API key, no announced rate limit.
- The ``yfinance`` package is already a dependency (see ``requirements.txt``).
- Returns 1-day bars for >10 years for every supported US ticker.

Why publish to Kafka instead of writing straight to Bronze:
- Keeps the medallion pipeline single-source-of-truth: every OHLCV row
  entering the lakehouse is consumed from the same ``stock-ohlcv-raw``
  topic by :mod:`app.streaming.kafka_consumer`, regardless of whether it
  came from a real-time WebSocket tick, the VN REST poller, or this
  end-of-day poller.
- The consumer is idempotent on ``(symbol, timestamp)`` so re-publishing
  the same bar is safe.

Source tag written to Bronze: ``"yfinance_eod"`` — lets the lineage
column distinguish EOD bars from real-time ticks.

Usage::

    python -m app.streaming.yfinance_eod_poller --symbols AAPL,MSFT --duration 60

Or run via the FastAPI lifespan hook in :mod:`app.main`, gated by the
``US_EOD_POLLER_ENABLED`` env var (default off).
"""

from __future__ import annotations

import threading
import time

import pandas as pd

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.constants import OHLCV_COLUMNS
from app.data_sources.yfinance_python_provider import YFinancePythonProvider
from app.streaming.kafka_producer import (
    DEFAULT_BOOTSTRAP_SERVERS,
    StockKafkaProducer,
    TOPIC_OHLCV_RAW,
)

logger = get_logger(__name__)


class YFinanceEodPoller:
    """Poll yfinance for 1-day bars and republish to Kafka.

    Default cadence is **1 hour** — EOD bars do not need second-level
    freshness, and yfinance is occasionally throttled when hammered.
    Set ``poll_interval_seconds`` lower (e.g. 300s) for more frequent
    back-fill during a demo.
    """

    SOURCE_TAG = "yfinance_eod"
    POLL_INTERVAL = 3600  # 1 hour
    LOOKBACK_DAYS = 5     # last 5 trading days per tick — enough to backfill weekends/holidays

    def __init__(
        self,
        symbols: list[str] | None = None,
        kafka_topic: str = TOPIC_OHLCV_RAW,
        bootstrap_servers: str | None = None,
        poll_interval_seconds: int = POLL_INTERVAL,
        lookback_days: int = LOOKBACK_DAYS,
        inter_symbol_delay: float = 0.5,
    ) -> None:
        self.symbols = [
            s.strip().upper()
            for s in (symbols or settings.us_eod_poller_symbols.split(","))
            if s.strip()
        ]
        self.topic = kafka_topic
        self.bootstrap_servers = (
            bootstrap_servers
            or settings.kafka_bootstrap_servers
            or DEFAULT_BOOTSTRAP_SERVERS
        )
        self.poll_interval_seconds = max(60, poll_interval_seconds)
        self.lookback_days = lookback_days
        # Spacing between consecutive yfinance requests inside a single tick.
        # ~0.5s keeps 20 tickers = ~10s, well below the unofficial ~2k req/hour
        # cap from a single IP, and avoids triggering Yahoo's 429s.
        self.inter_symbol_delay = max(0.0, inter_symbol_delay)

        self._provider = YFinancePythonProvider()
        # ``StockKafkaProducer`` initialises the underlying kafka-python
        # client lazily; we only instantiate our wrapper here.
        self._producer = StockKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        self._thread: threading.Thread | None = None
        self._running = False
        # Per-symbol "last published timestamp" cursor so we never
        # republish a bar we've already seen.
        self._last_published: dict[str, pd.Timestamp] = {}

    # --------------------------------------------------------------- public

    def start(self) -> None:
        if self._running:
            logger.warning("YFinanceEodPoller already running")
            return
        if not self.symbols:
            raise ValueError(
                "YFinanceEodPoller needs at least one symbol "
                "(set US_EOD_POLLER_SYMBOLS in .env or pass symbols=[...])."
            )
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="yfinance-eod-poller"
        )
        self._thread.start()
        logger.info(
            "YFinanceEodPoller started: topic=%s symbols=%d every=%ds lookback=%dd",
            self.topic,
            len(self.symbols),
            self.poll_interval_seconds,
            self.lookback_days,
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
        logger.info("YFinanceEodPoller stopped")

    def fetch_once(self) -> dict[str, int]:
        """Run one tick synchronously. Returns ``{symbol: bars_published}``.

        Useful for smoke tests and the ``scripts/test_yfinance_eod.py`` helper.
        """
        results: dict[str, int] = {}
        end_ts = pd.Timestamp.now(tz="UTC")
        start_ts = end_ts - pd.Timedelta(days=self.lookback_days)
        for symbol in self.symbols:
            try:
                results[symbol] = self._poll_symbol(symbol, start_ts, end_ts)
            except Exception as exc:  # noqa: BLE001
                logger.debug("yfinance EOD poll failed for %s: %s", symbol, exc)
                results[symbol] = 0
            # Throttle so we don't hit yfinance's 429 limit. Skip the wait
            # for the last symbol so the tick finishes promptly.
            if self.inter_symbol_delay and symbol is not self.symbols[-1]:
                time.sleep(self.inter_symbol_delay)
        return results

    # --------------------------------------------------------------- internals

    def _loop(self) -> None:
        while self._running:
            try:
                self.fetch_once()
            except Exception as exc:  # noqa: BLE001 - daemon loop must not die
                logger.warning("YFinanceEodPoller tick error: %s", exc)
            # Sleep in 1s slices so stop() is responsive.
            for _ in range(self.poll_interval_seconds):
                if not self._running:
                    return
                time.sleep(1)

    def _poll_symbol(
        self,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> int:
        try:
            frame = self._provider.get_historical_data(
                symbol=symbol,
                start=start.to_pydatetime() if hasattr(start, "to_pydatetime") else start,
                end=end.to_pydatetime() if hasattr(end, "to_pydatetime") else end,
                interval="1d",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("yfinance history fetch failed for %s: %s", symbol, exc)
            return 0

        if frame is None or frame.empty:
            return 0

        # Filter to only columns Kafka needs (drop any extras the provider
        # added) and rewrite ``source`` so lineage is unambiguous.
        frame = frame[OHLCV_COLUMNS].copy()
        frame["source"] = self.SOURCE_TAG
        frame["ingestion_time"] = pd.Timestamp.now(tz="UTC")

        # Drop bars we've already published.
        last_ts = self._last_published.get(symbol)
        if last_ts is not None:
            frame = frame[frame["timestamp"] > last_ts]
        if frame.empty:
            return 0

        try:
            sent = self._producer.send_ohlcv_stream(
                symbol, frame, topic=self.topic
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("YFinanceEodPoller Kafka send failed for %s: %s", symbol, exc)
            return 0

        if sent:
            self._last_published[symbol] = frame["timestamp"].max()
            logger.info(
                "YFinanceEodPoller published %d new 1d bar(s) for %s (latest=%s)",
                sent,
                symbol,
                frame["timestamp"].max(),
            )
        return sent


# ── CLI helper ────────────────────────────────────────────────────────────────

def parse_args():  # pragma: no cover - CLI helper
    import argparse

    parser = argparse.ArgumentParser(
        description="Poll yfinance for 1-day US OHLCV bars and publish to Kafka."
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated tickers (default: US_EOD_POLLER_SYMBOLS from .env)",
    )
    parser.add_argument("--topic", default=TOPIC_OHLCV_RAW)
    parser.add_argument(
        "--bootstrap",
        default=settings.kafka_bootstrap_servers or DEFAULT_BOOTSTRAP_SERVERS,
    )
    parser.add_argument(
        "--interval", type=int, default=YFinanceEodPoller.POLL_INTERVAL,
        help="Poll interval in seconds (default 3600 = 1h)",
    )
    parser.add_argument(
        "--duration", type=int, default=0,
        help="Stop after N seconds (0 = run forever). Useful for smoke tests.",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single tick then exit (no Kafka producer required).",
    )
    return parser.parse_args()


def _main():  # pragma: no cover - CLI helper
    args = parse_args()
    symbols = (
        [s.strip() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else None
    )
    if args.once:
        # Smoke-test path: just fetch + print, no Kafka needed.
        poller = YFinanceEodPoller(
            symbols=symbols,
            poll_interval_seconds=args.interval,
        )
        results = poller.fetch_once()
        for sym, count in results.items():
            print(f"  {sym}: {count} new bar(s)")
        return

    poller = YFinanceEodPoller(
        symbols=symbols,
        kafka_topic=args.topic,
        bootstrap_servers=args.bootstrap,
        poll_interval_seconds=args.interval,
    )
    poller.start()
    try:
        if args.duration > 0:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        poller.stop()


if __name__ == "__main__":  # pragma: no cover
    _main()
