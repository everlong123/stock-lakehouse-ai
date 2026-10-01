"""Market data service reading from Gold/Silver/Bronze.

When the lakehouse is empty (e.g. demo without a pre-populated Bronze layer),
the service generates deterministic synthetic OHLCV data so the UI is still
usable. Synthetic data is clearly marked via `source_layer = 'synthetic_demo'`.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.core.constants import SUPPORTED_SYMBOLS
from app.core.exceptions import NotFoundError
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer


class MarketService:
    """Read OHLCV from the lakehouse, preferring Gold then Silver then Bronze."""

    def get_history(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        frame = GoldLayer().read(symbol)
        source_layer = "gold"
        if frame.empty:
            frame = SilverLayer().read(symbol)
            source_layer = "silver"
        if frame.empty:
            frame = BronzeLayer().read(symbol)
            source_layer = "bronze"
        if frame.empty:
            frame = self._synthetic_history(symbol, interval=interval)
            source_layer = "synthetic_demo"
        frame = frame.sort_values("timestamp")
        if start:
            frame = frame[frame["timestamp"] >= pd.Timestamp(start, tz="UTC")]
        if end:
            frame = frame[frame["timestamp"] <= pd.Timestamp(end, tz="UTC")]
        if frame.empty:
            raise NotFoundError("No market data available for the selected range.")
        frame = frame.copy()
        frame = frame.loc[:, ~frame.columns.duplicated()]
        frame["layer"] = source_layer
        frame["interval"] = interval
        return frame.reset_index(drop=True)

    def get_latest(self, symbol: str, interval: str = "1d") -> dict:
        frame = self.get_history(symbol, interval=interval)
        last = frame.iloc[-1]
        prev_close = float(frame.iloc[-2]["close"]) if len(frame) > 1 else float(last["close"])
        change_pct = (float(last["close"]) - prev_close) / prev_close if prev_close else 0.0
        return {
            "symbol": symbol.upper(),
            "timestamp": str(last["timestamp"]),
            "open": float(last["open"]),
            "high": float(last["high"]),
            "low": float(last["low"]),
            "close": float(last["close"]),
            "adj_close": float(last.get("adj_close", last["close"])),
            "volume": float(last["volume"]),
            "change_pct": change_pct,
            "source_layer": last.get("layer", "gold"),
            "interval": interval,
        }

    def to_records(self, frame: pd.DataFrame, limit: int = 1500) -> list[dict]:
        subset = frame.tail(limit)
        records = []
        for row in subset.itertuples(index=False):
            records.append(
                {
                    "symbol": str(getattr(row, "symbol", "")),
                    "timestamp": str(row.timestamp),
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                    "adj_close": float(getattr(row, "adj_close", row.close)),
                    "volume": float(row.volume),
                    "source": str(getattr(row, "source", "lakehouse")),
                }
            )
        return records

    def _synthetic_history(self, symbol: str, interval: str = "1d", n_bars: int = 252) -> pd.DataFrame:
        """Generate deterministic synthetic OHLCV so demo UI works without a populated lakehouse."""
        # Deterministic seed per symbol so each refresh gives the same series
        seed = sum(ord(c) for c in symbol.upper())
        rng = np.random.default_rng(seed)
        # Base price depends on whether symbol is "high-priced" (US big tech) or "low" (VN banks)
        base_price = 95 + (seed % 60) if symbol.upper() not in {
            "VCB", "TCB", "MBB", "ACB", "BID", "FPT", "HPG", "VHM", "VNM",
        } else 25 + (seed % 30)
        # Random walk
        returns = rng.normal(loc=0.0006, scale=0.018, size=n_bars)
        # Add a sine wave so charts look interesting
        wave = np.array([math.sin(i / 18.0) * 0.003 for i in range(n_bars)])
        prices = base_price * np.exp(np.cumsum(returns + wave))
        opens = np.concatenate([[prices[0]], prices[:-1]])
        closes = prices
        # Daily range
        daily_range = np.abs(rng.normal(loc=0.012, scale=0.006, size=n_bars)) * prices
        high = np.maximum(opens, closes) + daily_range * 0.55
        low = np.minimum(opens, closes) - daily_range * 0.55
        volume = rng.integers(low=800_000, high=8_000_000, size=n_bars).astype(float)

        # Time index
        now_utc = datetime.now(timezone.utc)
        if interval == "1d":
            # Use pandas.Timestamp so we can call .normalize() in one place
            end_ts = pd.Timestamp(now_utc).normalize()
            idx = pd.date_range(end=end_ts, periods=n_bars, freq="B")
        elif interval == "1h":
            idx = pd.date_range(end=now_utc, periods=n_bars, freq="h")
        elif interval == "15m":
            idx = pd.date_range(end=now_utc, periods=n_bars, freq="15min")
        else:
            idx = pd.date_range(end=now_utc, periods=n_bars, freq="5min")

        return pd.DataFrame(
            {
                "symbol": symbol.upper(),
                "timestamp": idx.tz_localize("UTC") if idx.tz is None else idx,
                "open": opens,
                "high": high,
                "low": low,
                "close": closes,
                "adj_close": closes,
                "volume": volume,
                "source": "synthetic_demo",
                "ingestion_time": datetime.now(timezone.utc),
            }
        )