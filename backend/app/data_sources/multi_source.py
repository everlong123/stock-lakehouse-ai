"""Multi-source adapter with automatic failover.

Given an ordered list of provider names, this adapter attempts each in turn
until one returns non-empty data.  The chain is configurable per interval
because Finnhub Free tier caps intraday lookback while yfinance and the
HTTP direct provider can return more history.

Typical usage:

    from app.data_sources.multi_source import MultiSourceProvider

    adapter = MultiSourceProvider([
        "yfinance",        # primary - widest lookback, no key
        "finnhub",         # backup if API key configured
        "web_scraper",     # last resort - direct HTTP scrape
    ])
    frame = adapter.get_historical_data("AAPL", interval="1d")
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Sequence

import pandas as pd

from app.core.exceptions import DataSourceError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Circuit-breaker tuning. A provider that keeps failing (expired key, exhausted
# daily quota, endpoint removed upstream) otherwise pays its full timeout on
# every single symbol. With 958 symbols that dominates the pass. After
# FAILURE_THRESHOLD consecutive failures the provider is skipped for
# COOLDOWN_SECONDS, then allowed one probe to see whether it recovered.
FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 900.0

# Only *configuration / quota* failures justify dropping a provider. A 404 for one
# symbol (delisted ticker, bad suffix) is a data problem, not a provider problem:
# the very next symbol usually succeeds, so counting those toward the breaker
# would disable a perfectly healthy provider and fail symbols that do have data.
# Patterns below match the real messages:
#   - "rate limit", "25 requests per day"      (Alpha Vantage free key exhausted)
#   - "authentication failed", "API key"       (Finnhub key missing/revoked)
#   - "premium plans"                          (upstream plan required)
_FATAL_PATTERNS = (
    "rate limit",
    "requests per day",
    "authentication failed",
    "api key",
    "premium plan",
    "subscription",
)


def _is_fatal_provider_error(message: str) -> bool:
    """True when the error means the provider itself is unusable right now."""
    lowered = message.lower()
    return any(pattern in lowered for pattern in _FATAL_PATTERNS)


# Recommended fallback chains per interval.  For US daily bars we prefer
# yahoo_http (direct v8 chart API, 10y+ history, no key) and fall through
# to the official yfinance package, then Finnhub / Alpha Vantage (key-based),
# finally web_scraper as a last resort.  Stooq is excluded from the daily
# chain because their public CSV endpoint now requires a JS challenge that
# cannot be solved from a server-side script.
DEFAULT_CHAINS: dict[str, list[str]] = {
    "1d": ["yahoo_http", "yfinance", "finnhub", "alpha_vantage", "web_scraper"],
}


class MultiSourceProvider:
    """Try a chain of providers until one yields non-empty data."""

    def __init__(self, sources: Sequence[str] | None = None) -> None:
        # Lazy import to avoid a circular dependency with factory.py.
        from app.data_sources.factory import get_data_provider

        self._sources = list(sources or DEFAULT_CHAINS["1d"])
        self._providers = {name: get_data_provider(name) for name in self._sources}
        # provider name -> (consecutive_failures, disabled_until_monotonic)
        self._breaker: dict[str, tuple[int, float]] = {}
        self._breaker_lock = threading.Lock()

    def _is_available(self, name: str) -> bool:
        """Return False while `name` is in its cooldown window."""
        with self._breaker_lock:
            entry = self._breaker.get(name)
            if entry is None:
                return True
            failures, disabled_until = entry
            if failures < FAILURE_THRESHOLD:
                return True
            if time.monotonic() >= disabled_until:
                # Cooldown elapsed: let one probe through to test recovery.
                self._breaker[name] = (0, 0.0)
                return True
            return False

    def _record_success(self, name: str) -> None:
        with self._breaker_lock:
            if self._breaker.get(name, (0, 0))[0]:
                logger.info("[%s] recovered after failures, back in the chain", name)
            self._breaker[name] = (0, 0.0)

    def _record_failure(self, name: str, message: str = "") -> None:
        """Count a failure toward the breaker, but only for fatal provider errors.

        Per-symbol problems (404 for a delisted ticker, empty frame) are logged
        but never counted: they say nothing about the provider's health, and
        counting them would knock out a working provider as soon as a few
        consecutive symbols happen to be delisted.
        """
        if not _is_fatal_provider_error(message):
            return
        with self._breaker_lock:
            failures, _ = self._breaker.get(name, (0, 0.0))
            failures += 1
            disabled_until = 0.0
            if failures >= FAILURE_THRESHOLD:
                disabled_until = time.monotonic() + COOLDOWN_SECONDS
                logger.warning(
                    "[%s] unusable (%d consecutive config/quota failures); "
                    "skipping it for %.0fs",
                    name, failures, COOLDOWN_SECONDS,
                )
            self._breaker[name] = (failures, disabled_until)

    @property
    def source_name(self) -> str:
        return "multi_source"

    @property
    def sources(self) -> list[str]:
        return list(self._sources)

    def get_historical_data(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Return the first non-empty frame from any provider in the chain."""

        errors: dict[str, str] = {}
        for name in self._sources:
            if not self._is_available(name):
                # Already in cooldown; record it as skipped so the final
                # "all providers failed" message still explains the gap.
                errors[name] = "skipped: unusable after repeated config/quota failures"
                continue
            provider = self._providers[name]
            try:
                frame = provider.get_historical_data(
                    symbol=symbol, start=start, end=end, interval=interval
                )
            except DataSourceError as exc:
                errors[name] = str(exc)
                self._record_failure(name, str(exc))
                logger.warning("[%s] failed for %s: %s", name, symbol, exc)
                continue
            except Exception as exc:  # noqa: BLE001
                errors[name] = f"{type(exc).__name__}: {exc}"
                self._record_failure(name, errors[name])
                logger.warning("[%s] errored for %s: %s", name, symbol, exc)
                continue

            if frame is None or frame.empty:
                errors[name] = "empty frame"
                logger.info("[%s] returned empty frame for %s", name, symbol)
                continue

            logger.info(
                "[%s] returned %d rows for %s (%s)",
                name,
                len(frame),
                symbol,
                interval,
            )
            self._record_success(name)
            return frame

        raise DataSourceError(
            f"All providers failed for {symbol} ({interval}): {errors}"
        )

    def get_latest_data(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        return self.get_historical_data(symbol=symbol, interval=interval).tail(1).reset_index(drop=True)

    def validate_symbol(self, symbol: str) -> bool:
        for name in self._sources:
            try:
                if self._providers[name].validate_symbol(symbol):
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    def get_news(self, symbol: str, limit: int = 20) -> pd.DataFrame:
        """Best-effort news retrieval - aggregates from every provider that supports it."""

        frames: list[pd.DataFrame] = []
        for name in self._sources:
            provider = self._providers[name]
            fetch = getattr(provider, "get_news", None)
            if not callable(fetch):
                continue
            try:
                frame = fetch(symbol, limit=limit)
            except Exception:  # noqa: BLE001
                continue
            if frame is not None and not frame.empty:
                frames.append(frame)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["title"])


def build_default_adapter(interval: str = "1d") -> MultiSourceProvider:
    """Return a multi-source adapter configured for the given interval."""

    return MultiSourceProvider(DEFAULT_CHAINS.get(interval, DEFAULT_CHAINS["1d"]))