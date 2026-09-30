"""SSI iBoard provider for Vietnamese stock historical OHLCV.

SSI (Saigon Securities) hosts a public chart API at
``iboard-api.ssi.com.vn/statistics/charts/history`` that returns long history
(many years, daily resolution) for any ticker listed on HOSE/HNX/UPCOM.

Free, no auth, no rate-limit announced (we add a sensible per-call sleep).

Response format::

    {
      "code": "SUCCESS",
      "data": {
        "t": [unix_seconds, ...],   # bar timestamps (UTC midnight)
        "o": [open, ...],            # open price (thousand VND)
        "h": [high, ...],            # high price
        "l": [low, ...],             # low price
        "c": [close, ...],           # close price
        "v": [volume, ...],          # matched volume (shares)
        "s": "ok"
      }
    }

Notes:
- Prices are in *thousands* of VND. We convert to VND by multiplying
  ``open/high/low/close`` by 1,000 so the lakehouse stores absolute VND.
- Some symbols (HNX, UPCOM) are also supported but data may be sparser.
- Sundays and Vietnamese holidays are absent from the series.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import requests

from app.core.config import settings
from app.core.constants import OHLCV_COLUMNS
from app.core.exceptions import DataSourceError, DataValidationError
from app.core.logging_config import get_logger
from app.data_sources.base import StockDataProvider

logger = get_logger(__name__)


# Resolution mapping: yfinance style -> TradingView style (used by SSI)
_RESOLUTION_MAP: dict[str, str] = {
    "1d": "1D",
    "1h": "60",
    "15m": "15",
    "5m": "5",
    "1m": "1",
}


class SSIVNProvider(StockDataProvider):
    """Fetch historical OHLCV from SSI iBoard for VN-listed tickers."""

    source_name = "ssi_vn"
    DEFAULT_URL = "https://iboard-api.ssi.com.vn/statistics/charts/history"
    DEFAULT_TIMEOUT = 20

    def __init__(self, timeout: int | None = None, rate_limit_sleep: float = 0.5) -> None:
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.rate_limit_sleep = rate_limit_sleep
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
                "Origin": "https://iboard.ssi.com.vn",
                "Referer": "https://iboard.ssi.com.vn/",
            }
        )

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _to_unix(dt: datetime) -> int:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())

    def _request(self, symbol: str, resolution: str, start_ts: int, end_ts: int) -> dict:
        params = {
            "symbol": symbol.upper(),
            "resolution": resolution,
            "from": start_ts,
            "to": end_ts,
        }
        try:
            response = self.session.get(
                self.DEFAULT_URL, params=params, timeout=self.timeout
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as exc:
            raise DataSourceError(f"SSI request failed for {symbol}: {exc}") from exc
        except ValueError as exc:
            raise DataSourceError(f"Invalid SSI response for {symbol}: {exc}") from exc

        if payload.get("code") != "SUCCESS":
            raise DataSourceError(
                f"SSI error for {symbol}: {payload.get('message', 'unknown')}"
            )

        data = payload.get("data") or {}
        timestamps = data.get("t") or []
        if not timestamps:
            raise DataSourceError(f"No data returned by SSI for {symbol}")

        return data

    @staticmethod
    def _normalize(data: dict, symbol: str) -> pd.DataFrame:
        t = data["t"]
        o = data["o"]
        h = data["h"]
        l = data["l"]
        c = data["c"]
        v = data.get("v") or [0] * len(t)

        # SSI returns prices in *thousands* of VND. Convert to absolute VND.
        records: list[dict] = []
        for i, ts in enumerate(t):
            try:
                open_p = float(o[i]) * 1000.0
                high_p = float(h[i]) * 1000.0
                low_p = float(l[i]) * 1000.0
                close_p = float(c[i]) * 1000.0
                volume = float(v[i]) if i < len(v) and v[i] is not None else 0.0
            except (TypeError, ValueError):
                # Skip rows with malformed numbers
                continue

            # Skip zero-price rows (defensive)
            if close_p <= 0:
                continue

            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            records.append(
                {
                    "timestamp": dt,
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                    "adj_close": close_p,
                    "volume": volume,
                }
            )

        if not records:
            raise DataSourceError(f"All rows malformed for {symbol}")

        frame = pd.DataFrame(records)
        frame["symbol"] = symbol.upper()
        frame["source"] = SSIVNProvider.source_name
        frame["ingestion_time"] = pd.Timestamp.now(tz="UTC")
        return frame[OHLCV_COLUMNS].sort_values("timestamp").reset_index(drop=True)

    # -------------------------------------------------------------- public API

    def validate_symbol(self, symbol: str) -> bool:
        """Return True if SSI has any data for the symbol (cheap probe)."""
        try:
            end = int(datetime.now(timezone.utc).timestamp())
            start = end - 30 * 86400  # last 30 days
            data = self._request(symbol, "1D", start, end)
            return bool(data.get("t"))
        except Exception as exc:
            logger.debug("validate_symbol(%s) failed: %s", symbol, exc)
            return False

    def get_historical_data(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        symbol = symbol.upper()
        if interval not in _RESOLUTION_MAP:
            raise DataValidationError(f"Unsupported interval: {interval}")

        resolution = _RESOLUTION_MAP[interval]
        end_dt = end or datetime.now(timezone.utc)
        start_dt = start or end_dt.replace(year=end_dt.year - 10)

        start_ts = self._to_unix(start_dt)
        end_ts = self._to_unix(end_dt)

        data = self._request(symbol, resolution, start_ts, end_ts)
        frame = self._normalize(data, symbol)

        # Apply explicit date filters
        if start is not None:
            start_utc = pd.Timestamp(start_dt)
            if start_utc.tzinfo is None:
                start_utc = start_utc.tz_localize("UTC")
            frame = frame[frame["timestamp"] >= start_utc]
        if end is not None:
            end_utc = pd.Timestamp(end_dt)
            if end_utc.tzinfo is None:
                end_utc = end_utc.tz_localize("UTC")
            frame = frame[frame["timestamp"] <= end_utc]

        if frame.empty:
            raise DataSourceError(
                f"No data returned by SSI for {symbol} in [{start_dt}, {end_dt}]"
            )

        # Gentle rate limit so we don't hammer the public endpoint
        if self.rate_limit_sleep > 0:
            time.sleep(self.rate_limit_sleep)

        logger.info(
            "Fetched %s rows from SSI for %s (resolution=%s, span=%s..%s)",
            len(frame),
            symbol,
            resolution,
            frame["timestamp"].min().date(),
            frame["timestamp"].max().date(),
        )
        return frame

    def get_latest_data(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        end = datetime.now(timezone.utc)
        start = end - pd.Timedelta(days=30)
        frame = self.get_historical_data(symbol=symbol, start=start, end=end, interval=interval)
        return frame.tail(1).reset_index(drop=True)
