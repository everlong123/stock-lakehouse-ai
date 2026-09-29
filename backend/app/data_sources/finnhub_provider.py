"""
Finnhub provider for real-time stock data.

Free tier: 60 requests/minute, all US stocks + Forex + Crypto (limited).
Sign up at: https://finnhub.io/  (free API key, no credit card).

This provider is used for **historical OHLCV** only - streaming data is
delivered by :mod:`app.streaming.finnhub_websocket` which uses the same
API key.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd
import requests

from app.core.config import settings
from app.core.constants import OHLCV_COLUMNS
from app.core.exceptions import DataSourceError
from app.core.logging_config import get_logger
from app.data_sources.base import StockDataProvider

logger = get_logger(__name__)


class FinnhubProvider(StockDataProvider):
    """Fetch OHLCV data via Finnhub API.

    Free tier supports US stocks, crypto and forex - perfect for a $0 budget
    academic project.  WebSocket streaming for tick-level data is implemented
    in :class:`app.streaming.finnhub_websocket.FinnhubWebSocketClient`.
    """

    source_name = "finnhub"

    BASE_URL = "https://finnhub.io/api/v1"

    # Map of our internal interval token -> Finnhub resolution code.
    INTERVAL_MAP: dict[str, str] = {
        "1d": "D",
        "1h": "60",
        "15m": "15",
        "5m": "5",
        "1m": "1",
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = (
            api_key
            or getattr(settings, "finnhub_api_key", None)
            or ""
        )
        # Finnhub requires authentication - if no key is set we still surface
        # a clear error at request time rather than using the public demo.
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "stock-lakehouse-ai/1.0 (+https://finnhub.io)",
            }
        )

    # ------------------------------------------------------------------ helpers

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key) and self.api_key != "demo"

    def _request(self, endpoint: str, params: dict | None = None) -> dict:
        if not self.has_credentials:
            raise DataSourceError(
                "Finnhub API key is not configured. Set FINNHUB_API_KEY in .env "
                "(free key from https://finnhub.io/)."
            )

        params = params.copy() if params else {}
        params["token"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=30)
        except requests.exceptions.RequestException as exc:
            raise DataSourceError(f"Finnhub request failed: {exc}") from exc

        if response.status_code == 401 or response.status_code == 403:
            raise DataSourceError(
                "Finnhub authentication failed. Check FINNHUB_API_KEY in .env."
            )
        if response.status_code == 429:
            raise DataSourceError(
                "Finnhub rate limit exceeded (60 req/min on Free tier). "
                "Wait ~60s and retry."
            )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise DataSourceError(f"Finnhub HTTP error: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise DataSourceError(f"Finnhub returned non-JSON payload: {exc}") from exc

        if isinstance(payload, dict) and payload.get("s") == "error":
            raise DataSourceError(
                f"Finnhub error: {payload.get('errmsg', 'Unknown error')}"
            )
        return payload

    # ----------------------------------------------------------- public API

    def validate_symbol(self, symbol: str) -> bool:
        if not self.has_credentials:
            return False
        try:
            payload = self._request("search", {"q": symbol})
            results = payload.get("result") or []
            return any(item.get("symbol", "").upper() == symbol.upper() for item in results)
        except Exception:
            return False

    def get_historical_data(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        symbol = symbol.upper()
        finnhub_resolution = self.INTERVAL_MAP.get(interval, "D")

        end = end or datetime.now(timezone.utc)
        start = start or end - timedelta(days=settings.default_lookback_days)

        # Cap lookback at Finnhub's documented free-tier limits.
        # 1 minute: 1 month.  Daily: 10+ years.
        max_days = {
            "1": 30,
            "5": 30,
            "15": 30,
            "30": 60,
            "60": 365,
            "D": 365 * 10,
        }.get(finnhub_resolution, 365 * 10)
        max_lookback = timedelta(days=max_days)
        if end - start > max_lookback:
            start = end - max_lookback

        params = {
            "symbol": symbol,
            "resolution": finnhub_resolution,
            "from": int(start.timestamp()),
            "to": int(end.timestamp()),
        }

        payload = self._request("stock/candle", params)

        if payload.get("s") == "no_data":
            raise DataSourceError(f"No candle data returned by Finnhub for {symbol}")

        timestamps = payload.get("t") or []
        opens = payload.get("o") or []
        highs = payload.get("h") or []
        lows = payload.get("l") or []
        closes = payload.get("c") or []
        volumes = payload.get("v") or []

        if not timestamps:
            raise DataSourceError(f"Finnhub returned empty payload for {symbol}")

        records: list[dict[str, Any]] = []
        for i, ts in enumerate(timestamps):
            try:
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            except (OverflowError, OSError, ValueError) as exc:
                logger.warning("Skipping Finnhub bar with bad timestamp %s: %s", ts, exc)
                continue

            records.append(
                {
                    "symbol": symbol,
                    "timestamp": dt,
                    "open": float(opens[i]) if i < len(opens) else 0.0,
                    "high": float(highs[i]) if i < len(highs) else 0.0,
                    "low": float(lows[i]) if i < len(lows) else 0.0,
                    "close": float(closes[i]) if i < len(closes) else 0.0,
                    "adj_close": float(closes[i]) if i < len(closes) else 0.0,
                    "volume": float(volumes[i]) if i < len(volumes) else 0.0,
                    "source": self.source_name,
                    "ingestion_time": pd.Timestamp.now(tz="UTC"),
                }
            )

        frame = pd.DataFrame(records, columns=OHLCV_COLUMNS)
        if frame.empty:
            raise DataSourceError(f"Finnhub returned no parseable bars for {symbol}")
        frame = frame.sort_values("timestamp").reset_index(drop=True)

        logger.info("Fetched %s rows from Finnhub for %s", len(frame), symbol)
        return frame

    def get_latest_data(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        end = datetime.now(timezone.utc)
        lookback_days = {
            "1d": 7,
            "1h": 24,
            "15m": 24,
            "5m": 24,
            "1m": 24,
        }.get(interval, 7)
        start = end - timedelta(days=lookback_days)
        frame = self.get_historical_data(symbol=symbol, start=start, end=end, interval=interval)
        return frame.tail(1).reset_index(drop=True)

    # ------------------------------------------------------------------ extras

    def get_company_info(self, symbol: str) -> dict[str, Any]:
        """Return company profile (used by AI Agent fundamentals tool)."""

        return self._request("stock/profile2", {"symbol": symbol.upper()})

    def get_news(self, symbol: str, days_back: int = 7, limit: int = 50) -> pd.DataFrame:
        """Return company news from Finnhub's ``company-news`` endpoint."""

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)

        payload = self._request(
            "company-news",
            {
                "symbol": symbol.upper(),
                "from": start.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
            },
        )

        if not isinstance(payload, list):
            return pd.DataFrame()

        records: list[dict[str, Any]] = []
        for item in payload[:limit]:
            ts = item.get("datetime")
            try:
                published = (
                    datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    if ts is not None
                    else None
                )
            except (OverflowError, OSError, ValueError):
                published = None

            records.append(
                {
                    "symbol": symbol.upper(),
                    "title": item.get("headline", ""),
                    "summary": item.get("summary", ""),
                    "source": item.get("source", ""),
                    "link": item.get("url", ""),
                    "published_at": published,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "provider": self.source_name,
                }
            )

        return pd.DataFrame(records)

    def search_symbols(self, query: str) -> list[dict[str, Any]]:
        """Return Finnhub search results for ``query``."""

        payload = self._request("search", {"q": query})
        return payload.get("result") or []

    def health_check(self) -> bool:
        """Lightweight connectivity test used by the data_ingestion_service."""

        if not self.has_credentials:
            return False
        try:
            # ``search`` is the cheapest endpoint that still requires auth.
            self._request("search", {"q": "AAPL"})
            return True
        except DataSourceError:
            return False