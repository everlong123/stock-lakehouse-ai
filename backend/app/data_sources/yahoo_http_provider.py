"""Yahoo Finance HTTP provider - direct REST call, no yfinance package needed.

Uses the public Yahoo Finance v8 chart API with browser User-Agent.
Returns up to ~10 years of OHLCV history for any US ticker.

URL: https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}
     ?period1={unix_start}&period2={unix_end}&interval=1d&events=history
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests

from app.core.config import settings
from app.core.constants import OHLCV_COLUMNS
from app.core.exceptions import DataSourceError
from app.core.logging_config import get_logger
from app.data_sources.base import StockDataProvider

logger = get_logger(__name__)


class YahooHttpProvider(StockDataProvider):
    """Fetch OHLCV via direct Yahoo Finance v8 chart endpoint.

    This provider does NOT require the `yfinance` Python package - it uses
    plain HTTP requests with a browser User-Agent header to bypass Yahoo's
    bot detection.  Returns up to 10+ years of daily history for US tickers.
    """

    source_name = "yahoo_http"

    CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, timeout: int | None = None):
        self.timeout = timeout or settings.yfinance_timeout or 30
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://finance.yahoo.com",
            "Referer": "https://finance.yahoo.com/",
            "Connection": "keep-alive",
        })

    def _to_yahoo_symbol(self, symbol: str) -> str:
        """Add .VN for VN tickers (basic, without external provider)."""
        symbol = symbol.upper()
        vn_set = {"VCB", "TCB", "MBB", "ACB", "BID", "SSI", "VND", "VHM", "VRE", "KDH",
                   "FPT", "CMG", "MWG", "HPG", "GAS", "PLX", "POW", "VNM", "SAB", "MSN",
                   "VIC", "VPB", "CTG", "PNJ", "HDB", "STB", "TPB", "MSB", "SHB", "LPB",
                   "OCB", "REE", "NVL", "PDR", "BCM", "SBT", "IMP", "KDC", "PC1", "HDG",
                   "DRC", "DXG", "IDJ", "ITA", "JVC", "LSG", "MSH", "NSC", "PVT", "MBC",
                   "DIG", "FCN", "HCM", "CTC", "SMT", "KSC", "VGC", "BVH", "PNVN", "EIB"}
        if symbol in vn_set:
            return f"{symbol}.VN"
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
        yahoo_sym = self._to_yahoo_symbol(symbol)
        end_dt = end or datetime.now(timezone.utc)
        start_dt = start or (end_dt - pd.Timedelta(days=settings.default_lookback_days))

        period1 = int(start_dt.timestamp())
        period2 = int(end_dt.timestamp())

        url = self.CHART_URL.format(symbol=yahoo_sym)
        params = {
            "period1": period1,
            "period2": period2,
            "interval": interval,
            "includeAdjustedClose": "true",
            "events": "history",
        }

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise DataSourceError(f"Yahoo HTTP request failed for {symbol}: {exc}") from exc

        try:
            result = data["chart"]["result"][0]
        except (KeyError, IndexError, TypeError) as exc:
            err = data.get("chart", {}).get("error", {})
            msg = err.get("description", "unknown error") if isinstance(err, dict) else str(err)
            raise DataSourceError(f"Yahoo returned no data for {symbol}: {msg}") from exc

        ts_list = result.get("timestamp", [])
        if not ts_list:
            raise DataSourceError(f"Yahoo returned no timestamps for {symbol}")

        quote = result["indicators"]["quote"][0]
        adj_close = result["indicators"].get("adjclose", [{}])[0].get("adjclose", [])

        timestamps = pd.to_datetime(ts_list, unit="s", utc=True)
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "volume": quote.get("volume", []),
            "adj_close": adj_close if adj_close else quote.get("close", []),
        })

        # Drop rows where OHLC are all NaN (Yahoo sometimes has gaps)
        df = df.dropna(subset=["close"]).reset_index(drop=True)

        df["symbol"] = symbol
        df["source"] = self.source_name
        df["ingestion_time"] = datetime.now(timezone.utc)

        df = df[[c for c in OHLCV_COLUMNS if c in df.columns]]

        logger.info("[yahoo_http] returned %d rows for %s (%s -> %s)",
                     len(df), symbol,
                     df["timestamp"].min().date() if len(df) else "?",
                     df["timestamp"].max().date() if len(df) else "?")
        return df

    def get_latest_data(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        end = datetime.now(timezone.utc)
        start = end - pd.Timedelta(days=10)
        return self.get_historical_data(symbol, start=start, end=end, interval=interval).tail(1)