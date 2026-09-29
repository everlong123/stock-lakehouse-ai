"""Yahoo Finance provider backed by the official ``yfinance`` package.

This provider uses the third-party ``yfinance`` library (already listed in
``requirements.txt``) to fetch OHLCV, fundamentals and news.  It is the
preferred way to consume Yahoo data once the package is installed - the
direct REST wrapper (``YFinanceProvider``) remains as a fallback for
restricted environments where ``yfinance`` cannot be imported.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from app.core.config import settings
from app.core.constants import OHLCV_COLUMNS, SUPPORTED_INTERVALS
from app.core.exceptions import DataSourceError, DataValidationError
from app.core.logging_config import get_logger
from app.data_sources.base import StockDataProvider

logger = get_logger(__name__)


_INTERVAL_MAP: dict[str, str] = {
    "1d": "1d",
    "1h": "60m",
    "15m": "15m",
    "5m": "5m",
    "1m": "1m",
}


def _safe_yfinance_import() -> Any:
    """Import ``yfinance`` lazily and convert ``ImportError`` to ``DataSourceError``."""

    try:
        import yfinance as yf  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on user env
        raise DataSourceError(
            "The 'yfinance' package is required for YFinancePythonProvider. "
            "Install it via 'pip install yfinance>=0.2.40'."
        ) from exc
    return yf


class YFinancePythonProvider(StockDataProvider):
    """High-level Yahoo Finance provider using the ``yfinance`` package.

    Supports:
    - Historical OHLCV (1m/5m/15m/1h/1d) - subject to Yahoo's range rules
    - Latest quote via ``Ticker.history``
    - Company info, news and recommendations (used by AI Agent)
    """

    source_name = "yfinance_python"

    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or settings.yfinance_timeout or 30
        self._yf: Any | None = None

    @property
    def yf(self) -> Any:
        if self._yf is None:
            self._yf = _safe_yfinance_import()
        return self._yf

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _normalize(df: pd.DataFrame, symbol: str, source: str) -> pd.DataFrame:
        """Return a DataFrame conforming to :data:`OHLCV_COLUMNS`."""

        if df is None or df.empty:
            return pd.DataFrame(columns=OHLCV_COLUMNS)

        frame = df.copy()

        # Flatten multi-index (yfinance >=0.2.40 returns columns as MultiIndex)
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = [str(col[0]) for col in frame.columns]

        # Strip timezone if present
        if frame.index.tzinfo is not None:
            frame.index = frame.index.tz_convert("UTC")
        else:
            frame.index = frame.index.tz_localize("UTC")

        frame = frame.reset_index().rename(columns={"index": "timestamp", "Date": "timestamp"})
        if "Datetime" in frame.columns:
            frame = frame.rename(columns={"Datetime": "timestamp"})

        # Standardise column names (yfinance uses capitalised OHLCV names)
        rename_map = {
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
        frame = frame.rename(columns=rename_map)

        if "adj_close" not in frame.columns and "close" in frame.columns:
            frame["adj_close"] = frame["close"]

        for required in ("open", "high", "low", "close", "adj_close", "volume"):
            if required not in frame.columns:
                frame[required] = 0.0

        frame["symbol"] = symbol.upper()
        frame["source"] = source
        frame["ingestion_time"] = pd.Timestamp.now(tz="UTC")

        # Ensure dtypes
        for col in ("open", "high", "low", "close", "adj_close", "volume"):
            frame[col] = pd.to_numeric(frame[col], errors="coerce")

        return frame[OHLCV_COLUMNS]

    # -------------------------------------------------------------- public API

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
        if interval not in SUPPORTED_INTERVALS and interval not in _INTERVAL_MAP:
            raise DataValidationError(f"Unsupported interval: {interval}")

        yf_interval = _INTERVAL_MAP.get(interval, interval)

        # Yahoo Finance does not accept periods > range limits.
        # We translate explicit [start, end] to `period`/`start`/`end` arguments.
        period: str | None = None
        start_arg: str | None = None
        end_arg: str | None = None

        if start is None and end is None:
            period = "5y"
        elif start and end:
            days = max((end - start).days, 1)
            period = self._days_to_period(days, interval)
            # 1m / intraday only supports a 30 day window.
            if yf_interval in {"1m", "2m", "5m", "15m", "30m", "60m", "90m"}:
                period = "60d" if days > 60 else "1mo"
                start_arg = start.strftime("%Y-%m-%d")
                end_arg = end.strftime("%Y-%m-%d")
                period = None
        else:
            # Only one boundary supplied - use period
            period = self._days_to_period(
                730 if start is None else max((datetime.now(timezone.utc) - start).days, 1),
                interval,
            )

        ticker = self.yf.Ticker(symbol)
        try:
            if start_arg and end_arg:
                raw = ticker.history(
                    start=start_arg,
                    end=end_arg,
                    interval=yf_interval,
                    auto_adjust=False,
                    raise_errors=False,
                )
            else:
                raw = ticker.history(
                    period=period or "5y",
                    interval=yf_interval,
                    auto_adjust=False,
                    raise_errors=False,
                )
        except Exception as exc:
            raise DataSourceError(f"yfinance request failed for {symbol}: {exc}") from exc

        frame = self._normalize(raw, symbol, self.source_name)

        # Apply optional filters explicitly (yfinance may return extra history)
        if start is not None:
            start_ts = pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC")
            frame = frame[frame["timestamp"] >= start_ts]
        if end is not None:
            end_ts = pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC")
            frame = frame[frame["timestamp"] <= end_ts]

        if frame.empty:
            raise DataSourceError(f"No data returned by yfinance for {symbol} ({interval})")

        frame = frame.sort_values("timestamp").reset_index(drop=True)
        logger.info(
            "Fetched %s rows from yfinance for %s (interval=%s)",
            len(frame),
            symbol,
            interval,
        )
        return frame

    def get_latest_data(self, symbol: str, interval: str = "1d") -> pd.DataFrame:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=14)
        frame = self.get_historical_data(symbol=symbol, start=start, end=end, interval=interval)
        return frame.tail(1).reset_index(drop=True)

    # ------------------------------------------------------- auxiliary helpers

    @staticmethod
    def _days_to_period(days: int, interval: str) -> str:
        """Map a number of days to a Yahoo ``period`` token."""

        if interval in {"1m", "2m", "5m", "15m", "30m", "60m", "90m"}:
            return "60d" if days > 60 else "1mo"
        if days <= 5:
            return "5d"
        if days <= 30:
            return "1mo"
        if days <= 90:
            return "3mo"
        if days <= 180:
            return "6mo"
        if days <= 365:
            return "1y"
        if days <= 730:
            return "2y"
        if days <= 1825:
            return "5y"
        return "max"

    # ----------------------------------------------------------- extras / news

    def get_company_info(self, symbol: str) -> dict[str, Any]:
        """Return the static company profile (sector, market cap, ...)."""

        ticker = self.yf.Ticker(symbol.upper())
        try:
            info = ticker.info or {}
        except Exception as exc:
            raise DataSourceError(f"yfinance info() failed for {symbol}: {exc}") from exc

        if not info:
            return {}

        keys = (
            "longName",
            "shortName",
            "symbol",
            "sector",
            "industry",
            "country",
            "currency",
            "exchange",
            "marketCap",
            "website",
            "longBusinessSummary",
        )
        return {key: info.get(key) for key in keys if info.get(key) is not None}

    def get_news(self, symbol: str, limit: int = 20) -> pd.DataFrame:
        """Return a DataFrame of recent news items."""

        ticker = self.yf.Ticker(symbol.upper())
        try:
            items = ticker.news or []
        except Exception as exc:
            raise DataSourceError(f"yfinance news() failed for {symbol}: {exc}") from exc

        records: list[dict[str, Any]] = []
        for item in items[:limit]:
            content = item.get("content", item) if isinstance(item, dict) else {}
            ts = (
                item.get("providerPublishTime")
                or content.get("pubDate")
                or content.get("displayTime")
            )
            try:
                published = (
                    datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    if isinstance(ts, (int, float))
                    else str(ts)
                )
            except Exception:
                published = str(ts) if ts else datetime.now(timezone.utc).isoformat()

            records.append(
                {
                    "symbol": symbol.upper(),
                    "title": content.get("title") or item.get("title", ""),
                    "publisher": content.get("provider", {}).get("displayName")
                    if isinstance(content.get("provider"), dict)
                    else item.get("publisher"),
                    "link": content.get("canonicalUrl", {}).get("url")
                    if isinstance(content.get("canonicalUrl"), dict)
                    else item.get("link"),
                    "published_at": published,
                    "summary": content.get("summary", ""),
                    "source": self.source_name,
                }
            )

        return pd.DataFrame(records)