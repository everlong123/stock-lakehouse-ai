"""Yahoo Finance provider using direct API. Used when DATA_SOURCE=yfinance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from app.core.config import settings
from app.core.constants import OHLCV_COLUMNS, SUPPORTED_INTERVALS
from app.core.exceptions import DataSourceError, DataValidationError
from app.core.logging_config import get_logger
from app.data_sources.base import StockDataProvider

logger = get_logger(__name__)


class YFinanceProvider(StockDataProvider):
    """Fetch OHLCV via direct Yahoo Finance API calls."""

    source_name = "yfinance"
    
    YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def validate_symbol(self, symbol: str) -> bool:
        try:
            frame = self.get_latest_data(symbol)
            return not frame.empty
        except Exception:
            return False

    def _fetch(self, symbol: str, interval: str = "1d", range_: str = "5y") -> dict:
        """Fetch data from Yahoo Finance API directly.
        
        Note: range parameter may be unreliable, so we use period1/period2 
        for precise date ranges.
        """
        url = self.YAHOO_URL.format(symbol=symbol)
        params = {"interval": interval, "range": range_}
        
        try:
            response = requests.get(
                url, 
                params=params, 
                headers=self.HEADERS,
                timeout=30
            )
            
            if response.status_code == 429:
                raise DataSourceError(
                    "Yahoo Finance rate limit exceeded. "
                    "Try DATA_SOURCE=finnhub for real-time quotes, "
                    "or wait 24h for rate limit reset."
                )
            
            response.raise_for_status()
            data = response.json()
            
            # If range didn't return enough data, try with explicit dates
            result = data.get("chart", {}).get("result", [{}])
            if result:
                timestamps = result[0].get("timestamp", [])
                # If we have less than expected rows for the range, fetch with explicit dates
                expected_min = {
                    "5d": 5, "1mo": 20, "3mo": 60, "6mo": 120,
                    "1y": 250, "2y": 500, "5y": 1200, "10y": 2500
                }
                min_expected = expected_min.get(range_, 100)
                
                if len(timestamps) < min_expected // 2:
                    # Fetch with explicit dates instead
                    from datetime import datetime, timedelta
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=365 * 5)  # 5 years
                    
                    params = {
                        "period1": int(start_date.timestamp()),
                        "period2": int(end_date.timestamp()),
                        "interval": interval
                    }
                    response = requests.get(
                        url, 
                        params=params, 
                        headers=self.HEADERS,
                        timeout=30
                    )
                    response.raise_for_status()
                    return response.json()
            
            return data
            
        except requests.exceptions.RequestException as e:
            raise DataSourceError(f"Yahoo Finance request failed: {e}")

    def get_historical_data(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        symbol = symbol.upper()
        if interval not in SUPPORTED_INTERVALS:
            raise DataValidationError(f"Unsupported interval: {interval}")
        
        # Map to yfinance intervals
        interval_map = {
            "1d": "1d",
            "1h": "1h",
            "15m": "15m",
            "5m": "5m",
        }
        yf_interval = interval_map.get(interval, "1d")
        
        # Calculate range based on lookback
        if start and end:
            days = (end - start).days
            if days <= 7:
                range_ = "5d"
            elif days <= 30:
                range_ = "1mo"
            elif days <= 90:
                range_ = "3mo"
            elif days <= 180:
                range_ = "6mo"
            elif days <= 365:
                range_ = "1y"
            elif days <= 730:
                range_ = "2y"
            else:
                range_ = "5y"
        else:
            range_ = "5y"
        
        try:
            data = self._fetch(symbol, interval=yf_interval, range_=range_)
            
            chart = data.get("chart", {}).get("result", [{}])[0]
            timestamps = chart.get("timestamp", [])
            indicators = chart.get("indicators", {}).get("quote", [{}])[0]
            
            if not timestamps:
                raise DataSourceError(f"No data returned from Yahoo Finance for {symbol}")
            
            opens = indicators.get("open", [])
            highs = indicators.get("high", [])
            lows = indicators.get("low", [])
            closes = indicators.get("close", [])
            volumes = indicators.get("volume", [])
            
            # Get adjusted close if available
            adj_close = indicators.get("adjclose", [])
            if not adj_close:
                adj_close = closes
            
            records = []
            for i, ts in enumerate(timestamps):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                
                # Filter by date range
                if start and dt < start:
                    continue
                if end and dt > end:
                    continue
                
                records.append({
                    "symbol": symbol,
                    "timestamp": dt,
                    "open": float(opens[i]) if i < len(opens) and opens[i] is not None else 0,
                    "high": float(highs[i]) if i < len(highs) and highs[i] is not None else 0,
                    "low": float(lows[i]) if i < len(lows) and lows[i] is not None else 0,
                    "close": float(closes[i]) if i < len(closes) and closes[i] is not None else 0,
                    "adj_close": float(adj_close[i]) if i < len(adj_close) and adj_close[i] is not None else 0,
                    "volume": float(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
                    "source": self.source_name,
                    "ingestion_time": pd.Timestamp.now(tz="UTC"),
                })
            
            if not records:
                raise DataSourceError(f"No data in date range for {symbol}")
            
            df = pd.DataFrame(records)
            df = df[OHLCV_COLUMNS].sort_values("timestamp").reset_index(drop=True)
            
            logger.info("Fetched %s yfinance rows for %s", len(df), symbol)
            return df
            
        except DataSourceError:
            raise
        except Exception as e:
            raise DataSourceError(f"Yahoo Finance parse error: {e}") from e

    def get_latest_data(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=14)
        frame = self.get_historical_data(symbol=symbol, start=start, end=end, interval=interval)
        return frame.tail(1).reset_index(drop=True)
