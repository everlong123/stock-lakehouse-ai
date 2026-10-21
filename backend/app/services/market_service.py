"""Market data service — reads OHLCV strictly from the lakehouse (Gold → Silver → Bronze).

NO synthetic / sample / fallback data. If a symbol has no data in any layer,
`NotFoundError` is raised so the UI surfaces a clear "no data" state instead of
showing fake numbers.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

import pandas as pd

from app.core.constants import SUPPORTED_INTERVALS
from app.core.exceptions import DataValidationError, NotFoundError
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer

# Reading a symbol downloads every one of its year/month parquet partitions from
# MinIO, so a long-history ticker (e.g. "M" spans 2016-2026 => ~120 objects) took
# over two minutes per request. A small LRU cache keeps repeat views fast while
# bounding memory: MAX_CACHE_SYMBOLS is deliberately small because this process
# also hosts the FastAPI app and the host has no pagefile.
MAX_CACHE_SYMBOLS = 24
_cache_lock = threading.Lock()

# Second-level TTL on top of the LRU, so a symbol that no auto-refresh pass has
# touched still goes back to MinIO after this long. Without a TTL the cache only
# ever goes stale-until-restart, because `lru_cache` alone has no expiry. Kept
# short-ish to balance the ~120-object read cost against UI freshness.
CACHE_TTL_SECONDS = 60
# symbol -> (monotonic_timestamp, frame, source_layer)
_cache_store: dict[str, tuple[float, pd.DataFrame, str]] = {}


def _cache_get(symbol: str) -> tuple[pd.DataFrame, str] | None:
    with _cache_lock:
        hit = _cache_store.get(symbol)
        if hit is None:
            return None
        stored_at, frame, layer = hit
        if time.monotonic() - stored_at > CACHE_TTL_SECONDS:
            del _cache_store[symbol]
            return None
        return frame, layer


def _cache_put(symbol: str, frame: pd.DataFrame, layer: str) -> None:
    with _cache_lock:
        if len(_cache_store) >= MAX_CACHE_SYMBOLS:
            oldest = min(_cache_store.items(), key=lambda kv: kv[1][0])[0]
            del _cache_store[oldest]
        _cache_store[symbol] = (time.monotonic(), frame, layer)


def _load_symbol_frame_uncached(symbol: str) -> tuple[pd.DataFrame, str]:
    frame = GoldLayer().read(symbol)
    source_layer = "gold"
    if frame.empty:
        frame = SilverLayer().read(symbol)
        source_layer = "silver"
    if frame.empty:
        frame = BronzeLayer().read(symbol)
        source_layer = "bronze"
    return frame, source_layer


def _load_symbol_frame(symbol: str) -> tuple[pd.DataFrame, str]:
    """Load one symbol from Gold -> Silver -> Bronze, memoised with a short TTL.

    Returns:
        (frame, source_layer). Callers must treat the frame as read-only;
        `get_history` copies before adding columns.
    """
    cached = _cache_get(symbol)
    if cached is not None:
        return cached
    frame, source_layer = _load_symbol_frame_uncached(symbol)
    _cache_put(symbol, frame, source_layer)
    return frame, source_layer


def clear_symbol_cache() -> None:
    """Drop memoised symbol frames (call after a pipeline run writes new data)."""
    with _cache_lock:
        _cache_store.clear()


class MarketService:
    """Read OHLCV from the lakehouse, preferring Gold then Silver then Bronze."""

    def get_history(
        self,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        symbol = symbol.upper()
        # The lakehouse is single-interval: only daily bars are ever written, so
        # there is no interval-keyed partition to read from. Previously the value
        # was echoed back into the `interval` column while actually serving daily
        # bars, which silently mislabelled the payload.
        if interval not in SUPPORTED_INTERVALS:
            raise DataValidationError(
                f"Unsupported interval '{interval}'. This lakehouse ingests "
                f"{SUPPORTED_INTERVALS} only; no data exists for other intervals."
            )
        frame, source_layer = _load_symbol_frame(symbol)
        if frame.empty:
            raise NotFoundError(
                f"No lakehouse data for {symbol}. The auto-refresh service may still "
                f"be ingesting this symbol, or it is unavailable from the data provider."
            )
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

    def to_records(self, frame: pd.DataFrame, limit: int = 5000) -> list[dict]:
        # Cap payload to avoid huge JSON responses on long histories. Default
        # raised from 1500 → 5000 to cover ~20 years of 1d bars for a single
        # symbol, which is enough for any backtest chart in the UI.
        if limit is not None and limit > 0 and len(frame) > limit:
            frame = frame.tail(limit)
        records = []
        for row in frame.itertuples(index=False):
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
