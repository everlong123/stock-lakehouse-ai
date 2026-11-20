"""Market data service — reads OHLCV strictly from the lakehouse (Gold → Silver → Bronze).

NO synthetic / sample / fallback data. If a symbol has no data in any layer,
`NotFoundError` is raised so the UI surfaces a clear "no data" state instead of
showing fake numbers.
"""

from __future__ import annotations

import threading
import time
import os
from datetime import date, datetime

import pandas as pd

from app.core.constants import SUPPORTED_INTERVALS, currency_for_symbol
from app.core.exceptions import DataValidationError, NotFoundError
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse import frame_cache
from app.lakehouse.exchange_timezone import session_day_of
from app.lakehouse.gold import GoldLayer
from app.lakehouse.session import as_utc_timestamp, canonicalize_daily_sessions, slice_window
from app.lakehouse.silver import SilverLayer
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Reading a symbol downloads every one of its year/month parquet partitions from
# MinIO, so a long-history ticker (e.g. "M" spans 2016-2026 => ~120 objects) took
# over two minutes per request. An LRU cache keeps repeat views fast while
# bounding memory.
#
# WHY 24 WAS TOO SMALL
# ---------------------
# The lakehouse holds ~950 symbols, so a cache of 24 could not possibly hold
# the working set of a user browsing the stock list. Every symbol past the
# 24th evicted the one at the front, and the classic LRU-thrash followed:
#
#   30 symbols, cold ....... 81.1s   (2.70s per symbol)
#   the same 30 again ...... 19.0s   (0.63s per symbol - still mostly misses)
#
# Every one of those misses downloads ~121 parquet partitions from MinIO, so
# "browse many stocks" was effectively "download the entire lakehouse from
# scratch, over and over".
#
# WHY 256 IS SAFE HERE
# ---------------------
# The old comment said a small cache was needed because "the host has no
# pagefile". That is no longer true: `scripts/enable_pagefile.ps1` now
# configures a system-managed pagefile on C:, and the WSL VM is capped at
# 8GB (was 12GB). So there is room to cache.
#
# The memory cost is bounded and small: a cached frame is the symbol's daily
# bars plus the ~90 derived indicator columns, and the raw parquet that
# produced it is already released. Measured: ~3 MB per symbol, so 256
# symbols is roughly 750 MB - affordable, and it covers the whole stock
# list of a typical browsing session.
MAX_CACHE_SYMBOLS = int(os.getenv("MARKET_CACHE_SYMBOLS", "256"))
_cache_lock = threading.Lock()

# Second-level TTL on top of the LRU, so a symbol that no auto-refresh pass has
# touched still goes back to MinIO after this long. Without a TTL the cache only
# ever goes stale-until-restart, because `lru_cache` alone has no expiry.
#
# WHY 900s (was 60s, then 300s): a read pulls ~121 partition files out of
# MinIO, which costs ~1s when the box is idle but much more while the
# auto-refresh pass is running. With a short TTL the dashboard had to
# re-download the whole history of the symbol roughly once a minute, and
# each of those reads could land in the middle of the refresh pass and
# blow past the frontend's 90s timeout.
#
# Freshness is not lost by the long TTL: the auto-refresh pass invalidates
# the entry for a symbol the moment it rewrites that symbol
# (`invalidate_symbol_cache`), so newly ingested rows still surface at
# once. The TTL only governs how long an UNCHANGED symbol is re-read.
CACHE_TTL_SECONDS = 900
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
    return _canonicalize_read_frame(frame), source_layer


def _canonicalize_read_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Collapse a stored frame to one bar per trading day before it is served.

    WHY this is needed even though the Silver writer now canonicalises:
    the parquet files already on disk were written before that fix, and a
    re-ingest is not guaranteed to have run for every symbol. Serving the
    stored rows as-is would keep drawing two candles for a session and a
    hundred candles for a day that has intraday ticks.

    The read path is the LAST line of defence, so the UI is correct for
    every symbol immediately, not only after the next backfill. The same
    function is applied on write, so the two paths agree on the result.
    """
    if frame.empty or "timestamp" not in frame.columns:
        return frame
    try:
        canonical, _report = canonicalize_daily_sessions(frame)
    except Exception:  # noqa: BLE001 - never fail a read over a cosmetic issue
        logger.warning("Read-path canonicalisation failed; serving raw rows", exc_info=True)
        return frame
    return canonical if not canonical.empty else frame


def _as_utc_timestamp(value: datetime) -> pd.Timestamp:
    """A timezone-aware UTC timestamp from whatever the caller passed.

    WHY THIS EXISTS
    ---------------
    The API takes ``start`` and ``end`` as ISO strings, and the browser
    sends them WITH a timezone (``2026-05-14T00:00:00.000Z``). The old
    code called ``pd.Timestamp(value, tz="UTC")``, which refuses a value
    that already carries one:
    ``ValueError: Cannot pass a datetime or Timestamp with tzinfo with
    the tz parameter`` - so every ranged request failed with a 500.

    A naive value is read as UTC (the lakehouse stores UTC), and an
    aware value is converted to UTC.
    """
    return as_utc_timestamp(value)


def _load_symbol_latest_uncached(symbol: str) -> tuple[pd.DataFrame, str]:
    """The symbol's newest bar, read from the newest partition only.

    WHY THIS EXISTS
    ---------------
    The market tape shows a price strip for ten tickers, and each quote
    used to load the symbol's WHOLE history - ~121 monthly partitions
    from MinIO - only to look at the last row.

    Measured on 14/11/2026: the tape took 11.7 s cold and ~1.0 s
    afterwards. Reading the newest partition instead of the whole
    history brings it down to a listing plus one object download per
    symbol.

    The layer order is the same as the full read (Gold -> Silver ->
    Bronze), and the rows are the SAME stored rows - nothing is
    recomputed or invented.
    """
    for layer, source_layer in (
        (GoldLayer(), "gold"),
        (SilverLayer(), "silver"),
        (BronzeLayer(), "bronze"),
    ):
        frame = layer.read_newest(symbol)
        if not frame.empty:
            return _canonicalize_read_frame(frame), source_layer
    return pd.DataFrame(), "gold"


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


def _load_symbol_frame_window(
    symbol: str,
    since: date | None,
    until: date | None,
) -> tuple[pd.DataFrame, str]:
    """Load a symbol's rows inside a date window, layer by layer.

    WHY THIS EXISTS
    ---------------
    A ten-year daily symbol is stored as ~121 monthly partitions. The
    caller asked for a six-month window, so only six of them are needed
    - the other 115 were downloaded, parsed and discarded, which made the
    request cost scale with the symbol's HISTORY rather than with the
    window.

    The memoised full frame is preferred when it is already in memory:
    slicing it costs nothing, and reading six partitions would cost a
    round-trip. The windowed read is used only when the full frame has
    to be fetched anyway.
    """
    cached = _cache_get(symbol)
    if cached is not None:
        frame, source_layer = cached
        return slice_window(frame, since, until), source_layer

    layers = (
        (GoldLayer(), "gold"),
        (SilverLayer(), "silver"),
        (BronzeLayer(), "bronze"),
    )
    for layer, source_layer in layers:
        frame = layer.read_window(symbol, since=since, until=until)
        if not frame.empty:
            return _canonicalize_read_frame(frame), source_layer
    return pd.DataFrame(), "gold"


def clear_symbol_cache() -> None:
    """Drop memoised symbol frames (call after a pipeline run writes new data)."""
    with _cache_lock:
        _cache_store.clear()
    # The shared lakehouse cache holds the same frames, so it has to be
    # dropped as well - otherwise a rewritten symbol would keep serving
    # its pre-write rows from the other cache.
    frame_cache.clear_cached()


def invalidate_symbol_cache(symbol: str) -> None:
    """Drop only ONE symbol's memoised frame.

    WHY this exists next to `clear_symbol_cache`: the auto-refresh pass
    rebuilds Silver+Gold for ~950 symbols one after another, and it used to
    call `clear_symbol_cache()` after every single symbol. That wiped the
    *entire* cache each time, so any page the user had open (the dashboard
    reads a symbol's 121 parquet partitions from MinIO) was re-reading the
    whole lakehouse from scratch on every request — the request took minutes
    and the UI sat on a spinner until the frontend's 90s axios timeout fired.

    Invalidation only has to be per-symbol: the writer only changed the rows
    of the symbol it just rebuilt, and every other cached frame is still
    valid. `clear_symbol_cache()` stays for the full-pipeline path, where
    many symbols really do change at once.
    """
    with _cache_lock:
        _cache_store.pop(symbol.upper(), None)
    frame_cache.invalidate_cached("gold", symbol)
    frame_cache.invalidate_cached("silver", symbol)
    frame_cache.invalidate_cached("bronze", symbol)


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
        frame, source_layer = _load_symbol_frame_window(
            symbol,
            since=_as_utc_timestamp(start).date() if start is not None else None,
            until=_as_utc_timestamp(end).date() if end is not None else None,
        )
        if frame.empty:
            if start is not None or end is not None:
                raise NotFoundError(
                    f"No market data for {symbol} inside the selected range. "
                    f"The symbol may not be covered by the requested dates."
                )
            raise NotFoundError(
                f"No lakehouse data for {symbol}. The auto-refresh service may still "
                f"be ingesting this symbol, or it is unavailable from the data provider."
            )
        frame = frame.sort_values("timestamp")
        if start:
            frame = frame[frame["timestamp"] >= _as_utc_timestamp(start)]
        if end:
            frame = frame[frame["timestamp"] <= _as_utc_timestamp(end)]
        if frame.empty:
            raise NotFoundError("No market data available for the selected range.")
        frame = frame.copy()
        frame = frame.loc[:, ~frame.columns.duplicated()]
        frame["layer"] = source_layer
        frame["interval"] = interval
        return frame.reset_index(drop=True)

    def get_latest(self, symbol: str, interval: str = "1d") -> dict:
        """The symbol's newest bar, read WITHOUT loading its whole history.

        WHY THIS EXISTS
        ---------------
        The market tape shows ten tickers in the navigation bar, and the
        ``/stocks/{symbol}/latest`` endpoint serves one quote. Both used
        to call ``get_history``, which loads the symbol's WHOLE history -
        ~121 monthly partitions from MinIO - to look at the last row.

        Measured on 14/11/2026: the ten-symbol tape took 11.7 s cold
        and ~1.0 s warm, because each of the ten quotes pulled ~121
        objects out of MinIO.

        Now only the newest partitions are read. The rows are the SAME
        stored rows - the newest partition holds the symbol's most recent
        sessions - so the quote is the quote, not an approximation.

        The full frame is used when it is already in memory: slicing it
        costs nothing, while a partition download costs a round-trip.
        """
        symbol = symbol.upper()
        if interval not in SUPPORTED_INTERVALS:
            raise DataValidationError(
                f"Unsupported interval '{interval}'. This lakehouse ingests "
                f"{SUPPORTED_INTERVALS} only; no data exists for other intervals."
            )

        cached = _cache_get(symbol)
        if cached is not None:
            frame, source_layer = cached
            return self.latest_from_frame(symbol, frame, interval=interval)

        frame, source_layer = _load_symbol_latest_uncached(symbol)
        if frame.empty:
            raise NotFoundError(
                f"No lakehouse data for {symbol}. The auto-refresh service may still "
                f"be ingesting this symbol, or it is unavailable from the data provider."
            )
        frame = frame.copy()
        frame["layer"] = source_layer
        frame["interval"] = interval
        return self.latest_from_frame(symbol, frame, interval=interval)

    def latest_from_frame(
        self,
        symbol: str,
        frame: pd.DataFrame,
        interval: str = "1d",
    ) -> dict:
        """Build the "latest bar" summary from an ALREADY loaded frame.

        WHY THIS EXISTS
        ---------------
        ``get_latest`` used to call ``get_history`` again, so the
        ``/stocks/{symbol}`` endpoint loaded the symbol's ~121 parquet
        partitions from MinIO TWICE per request. The second load hit the
        memoised frame, so it was "only" CPU work - but it re-sorted,
        re-copied and re-indexed a 2532 x 92 DataFrame for nothing.

        The endpoint now loads the frame once and derives both the history
        and the latest bar from it.
        """
        last = frame.iloc[-1]
        prev_close = float(frame.iloc[-2]["close"]) if len(frame) > 1 else float(last["close"])
        change_pct = (float(last["close"]) - prev_close) / prev_close if prev_close else 0.0
        latest_day = session_day_of(last["timestamp"], symbol)
        age = max(0, (pd.Timestamp.now(tz="UTC").date() - latest_day).days) if latest_day else None
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
            "latest_session": latest_day.isoformat() if latest_day else None,
            "age_calendar_days": age,
            "data_status": "stale" if age is not None and age > 10 else "recent",
            # The unit of the price. Prices here are unitless, and VCB's
            # 53,500 and AAPL's 330 are both "close" - without this the
            # consumer labels every symbol as if it traded in dong.
            "currency": currency_for_symbol(symbol),
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
