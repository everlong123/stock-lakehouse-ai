"""
Finnhub provider for real-time stock data.

Free tier: 60 requests/minute
Sign up at: https://finnhub.io/
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

from app.core.config import settings
from app.core.constants import OHLCV_COLUMNS
from app.core.exceptions import DataSourceError
from app.core.logging_config import get_logger
from app.data_sources.base import StockDataProvider

logger = get_logger(__name__)


class FinnhubProvider(StockDataProvider):
    """Fetch OHLCV data via Finnhub API."""

    source_name = "finnhub"
    
    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: Optional[str] = None):
        # Finnhub free tier supports most US stocks
        self.api_key = api_key or getattr(settings, 'finnhub_api_key', None)
        if not self.api_key:
            logger.warning("Finnhub API key not set. Set FINNHUB_API_KEY in .env for real data.")
            self.api_key = "demo"  # Fallback to demo (limited)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def validate_symbol(self, symbol: str) -> bool:
        try:
            frame = self.get_latest_data(symbol)
            return not frame.empty
        except Exception:
            return False

    def _request(self, endpoint: str, params: dict = None) -> dict:
        """Make API request with rate limit handling."""
        params = params or {}
        params["token"] = self.api_key
        
        url = f"{self.BASE_URL}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 429:
                raise DataSourceError("Finnhub rate limit exceeded. Wait and retry.")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise DataSourceError(f"Finnhub request failed: {e}")

    def get_historical_data(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Get historical OHLCV data from Finnhub."""
        symbol = symbol.upper()
        
        # Finnhub uses unix timestamps
        end = end or datetime.now(timezone.utc)
        start = start or end - timedelta(days=settings.default_lookback_days)
        
        # Map interval to Finnhub format
        interval_map = {
            "1d": "D",   # Daily
            "1h": "60",  # Hourly
            "15m": "15", # 15 min
            "5m": "5",   # 5 min
        }
        finnhub_interval = interval_map.get(interval, "D")
        
        params = {
            "symbol": symbol,
            "from": int(start.timestamp()),
            "to": int(end.timestamp()),
            "resolution": finnhub_interval,
        }
        
        data = self._request("stock/candle", params)
        
        if data.get("s") == "no_data":
            raise DataSourceError(f"No data available for {symbol}")
        
        if data.get("s") == "error":
            raise DataSourceError(f"Finnhub error: {data.get('errmsg', 'Unknown')}")
        
        # Parse OHLCV data
        timestamps = data.get("t", [])
        opens = data.get("o", [])
        highs = data.get("h", [])
        lows = data.get("l", [])
        closes = data.get("c", [])
        volumes = data.get("v", [])
        
        if not timestamps:
            raise DataSourceError(f"No candle data returned for {symbol}")
        
        records = []
        for i, ts in enumerate(timestamps):
            records.append({
                "symbol": symbol,
                "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                "open": float(opens[i]) if i < len(opens) else 0,
                "high": float(highs[i]) if i < len(highs) else 0,
                "low": float(lows[i]) if i < len(lows) else 0,
                "close": float(closes[i]) if i < len(closes) else 0,
                "adj_close": float(closes[i]) if i < len(closes) else 0,
                "volume": float(volumes[i]) if i < len(volumes) else 0,
                "source": self.source_name,
                "ingestion_time": pd.Timestamp.now(tz="UTC"),
            })
        
        df = pd.DataFrame(records)
        if df.empty:
            raise DataSourceError(f"No data returned from Finnhub for {symbol}")
        
        logger.info("Fetched %s rows from Finnhub for %s", len(df), symbol)
        return df[OHLCV_COLUMNS].sort_values("timestamp").reset_index(drop=True)

    def get_latest_data(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        """Get latest quote for a symbol."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        frame = self.get_historical_data(symbol=symbol, start=start, end=end, interval=interval)
        return frame.tail(1).reset_index(drop=True)

    def get_company_info(self, symbol: str) -> dict:
        """Get company profile."""
        return self._request("stock/profile2", {"symbol": symbol})

    def search_symbols(self, query: str) -> list[dict]:
        """Search for symbols."""
        results = self._request("search", {"q": query})
        return results.get("result", [])
