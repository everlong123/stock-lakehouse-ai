"""Stooq.com provider - free CSV data, no API key, 30+ years history.

URL format: https://stooq.com/q/d/l/?s=AAPL.US&d1=20161001&d2=20261002&i=d
- s = symbol with .US suffix for US stocks
- d1 = start date (YYYYMMDD)
- d2 = end date (YYYYMMDD)
- i = interval (d=daily, h=hourly)

Stooq is a Polish financial data aggregator that provides free EOD data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from app.core.config import settings
from app.core.constants import OHLCV_COLUMNS
from app.core.exceptions import DataSourceError
from app.core.logging_config import get_logger
from app.data_sources.base import StockDataProvider

logger = get_logger(__name__)


class StooqProvider(StockDataProvider):
    """Fetch OHLCV data from Stooq.com free CSV endpoint."""

    source_name = "stooq"

    BASE_URL = "https://stooq.com/q/d/l/"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; research-project/1.0)",
            "Accept": "text/csv,application/csv",
        })

    def _to_stooq_symbol(self, symbol: str) -> str:
        """Convert AAPL -> AAPL.US for Stooq format."""
        symbol = symbol.upper()
        # VN symbols not supported by Stooq (only US/international)
        return symbol

    def validate_symbol(self, symbol: str) -> bool:
        try:
            frame = self.get_latest_data(symbol)
            return not frame.empty
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
        end = end or datetime.now(timezone.utc)
        start = start or datetime.now(timezone.utc)

        # Stooq only supports daily for US stocks (.US suffix)
        stooq_sym = f"{symbol}.US"
        d1 = start.strftime("%Y%m%d")
        d2 = end.strftime("%Y%m%d")

        url = f"{self.BASE_URL}?s={stooq_sym}&d1={d1}&d2={d2}&i=d"
        logger.info("[stooq] fetching %s (%s -> %s)", stooq_sym, d1, d2)

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            raise DataSourceError(f"Stooq request failed for {symbol}: {exc}") from exc

        # Stooq returns CSV with columns: Date,Open,High,Low,Close,Volume
        # It may return an error page if symbol not found
        text = response.text.strip()
        if not text or "Error" in text or "<html" in text.lower():
            raise DataSourceError(f"Stooq returned empty/error for {symbol}")

        # Parse CSV
        try:
            from io import StringIO
            df = pd.read_csv(StringIO(text), parse_dates=["Date"])
        except Exception as exc:
            raise DataSourceError(f"Stooq CSV parse failed for {symbol}: {exc}") from exc

        if df.empty:
            raise DataSourceError(f"Stooq returned empty frame for {symbol}")

        # Rename and standardize columns
        df = df.rename(columns={
            "Date": "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })

        # Add missing columns
        df["symbol"] = symbol
        df["adj_close"] = df["close"]  # Stooq doesn't provide adj_close separately
        df["source"] = self.source_name
        df["ingestion_time"] = datetime.now(timezone.utc)
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")

        # Ensure column order matches OHLCV_COLUMNS
        df = df[[c for c in OHLCV_COLUMNS if c in df.columns]]

        logger.info("[stooq] returned %d rows for %s", len(df), symbol)
        return df

    def get_latest_data(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        """Get just the latest daily bar."""
        end = datetime.now(timezone.utc)
        start = end - pd.Timedelta(days=30)
        return self.get_historical_data(symbol, start=start, end=end, interval=interval).tail(1)
