"""Market Index provider - fetches US market indices via Yahoo Finance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

from app.core.exceptions import DataSourceError
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class MarketIndexProvider:
    """Fetch US market indices: S&P 500, Dow Jones, NASDAQ via Yahoo Finance."""

    source_name = "market_index"

    # US Index symbols (Yahoo Finance format)
    INDEX_SYMBOLS = {
        "SP500": "^GSPC",      # S&P 500
        "DJI": "^DJI",         # Dow Jones Industrial Average
        "NASDAQ": "^IXIC",      # NASDAQ Composite
        "RUT": "^RUT",         # Russell 2000 (Small cap)
        "VIX": "^VIX",         # Volatility Index
    }
    
    # Reverse mapping: Yahoo symbol -> Display name
    INDEX_NAMES = {
        "^GSPC": "S&P 500",
        "^DJI": "Dow Jones",
        "^IXIC": "NASDAQ",
        "^RUT": "Russell 2000",
        "^VIX": "VIX",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/html",
        })

    def get_index_data(self, symbol: str = "^GSPC") -> pd.DataFrame:
        """Get historical data for a market index.
        
        Args:
            symbol: Can be display name (SP500, DJI, NASDAQ) or Yahoo symbol (^GSPC, ^DJI)
        """
        # Map display name to Yahoo symbol
        yahoo_symbol = self.INDEX_SYMBOLS.get(symbol.upper(), symbol.upper())
        # If not found in INDEX_SYMBOLS, try as-is (for raw Yahoo symbols)

        try:
            # Use Yahoo Finance
            response = self.session.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}",
                params={"interval": "1d", "range": "2y"},
                timeout=15,
            )

            if response.status_code != 200:
                logger.warning(f"Yahoo Finance returned {response.status_code} for {symbol}")
                return pd.DataFrame()

            data = response.json()
            result = data.get("chart", {}).get("result", [{}])[0]

            if not result:
                return pd.DataFrame()

            timestamps = result.get("timestamp", [])
            quotes = result.get("indicators", {}).get("quote", [{}])[0]

            if not timestamps:
                return pd.DataFrame()

            records = []
            for i, ts in enumerate(timestamps):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                close = quotes.get("close", [None])[i]
                high = quotes.get("high", [None])[i]
                low = quotes.get("low", [None])[i]
                open_price = quotes.get("open", [None])[i]
                volume = quotes.get("volume", [None])[i]

                if close:
                    records.append({
                        "symbol": symbol.upper(),
                        "timestamp": dt,
                        "open": open_price,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": volume,
                        "source": self.source_name,
                        "ingestion_time": pd.Timestamp.now(tz="UTC"),
                    })

            frame = pd.DataFrame(records)
            if not frame.empty:
                frame["change"] = frame["close"].pct_change() * 100
                frame["change_from_open"] = ((frame["close"] - frame["open"]) / frame["open"]) * 100
            return frame

        except Exception as exc:
            logger.warning(f"Failed to fetch {symbol}: {exc}")
            return pd.DataFrame()

    def get_all_indices(self) -> dict[str, pd.DataFrame]:
        """Get all major indices."""
        results = {}
        for display_name, yahoo_sym in self.INDEX_SYMBOLS.items():
            df = self.get_index_data(yahoo_sym)
            results[display_name] = df
        return results

    def get_index_summary(self, symbol: str = "^GSPC") -> dict[str, Any]:
        """Get current summary for an index."""
        df = self.get_index_data(symbol)

        if df.empty:
            return {"symbol": symbol, "error": "No data available"}

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        return {
            "symbol": symbol,
            "close": float(latest["close"]),
            "change": float(latest.get("change", 0)),
            "change_pct": float(latest.get("change", 0)),
            "volume": int(latest["volume"]) if pd.notna(latest["volume"]) else 0,
            "high_52w": float(df["high"].max()) if not df.empty else None,
            "low_52w": float(df["low"].min()) if not df.empty else None,
            "prev_close": float(prev["close"]),
            "timestamp": str(latest["timestamp"]),
        }

    def get_marketBreadth(self, date: str | None = None) -> dict[str, Any]:
        """Get market breadth (advance/decline, new high/low) - US markets.

        Not currently available: this requires a real-time tick-level feed which
        the project does not ingest. Raising instead of returning zeros so callers
        never mistake fabricated breadth for real data.
        """
        raise DataSourceError(
            "Market breadth requires a real-time tick feed which is not available. "
            "Use /market/indices/sectors for sector performance instead."
        )

    def get_sector_performance(self) -> pd.DataFrame:
        """Get US sector performance via Yahoo Finance."""
        # US Sector ETFs
        sector_map = {
            "XLK": "Technology",
            "XLF": "Financials",
            "XLE": "Energy",
            "XLV": "Healthcare",
            "XLY": "Consumer Discretionary",
            "XLP": "Consumer Staples",
            "XLI": "Industrials",
            "XLB": "Materials",
            "XLRE": "Real Estate",
            "XLU": "Utilities",
            "XLC": "Communication Services",
        }

        records = []
        for yahoo_sym, sector_name in sector_map.items():
            try:
                df = self.get_index_data(yahoo_sym)
                if not df.empty:
                    latest = df.iloc[-1]
                    year_change = (latest["close"] / df.iloc[0]["close"] - 1) * 100 if len(df) > 1 else 0

                    records.append({
                        "sector": sector_name,
                        "symbol": yahoo_sym,
                        "close": latest["close"],
                        "change_pct": latest.get("change", 0),
                        "year_change_pct": year_change,
                        "volume": latest["volume"] if pd.notna(latest["volume"]) else 0,
                    })
            except Exception:
                continue

        return pd.DataFrame(records)
