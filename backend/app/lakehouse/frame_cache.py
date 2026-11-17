"""A process-wide cache of the lakehouse frames the batch jobs read.

WHY THIS FILE EXISTS
--------------------
Reading a symbol from MinIO downloads every one of its monthly parquet
partitions. A 10-year daily ticker has ~121 of them, and the measured
cost of one read is ~0.5 s (13/11/2026, MinIO on the same host).

    10|The nightly universe pass reads 973 symbols. At 0.5 s each, read
SERIALLY, that is ~8 minutes of pure waiting - and the forecast itself
takes 0.06 s per symbol. The read was 90% of the cost.

So the pass does two things:

* it reads the symbols CONCURRENTLY (the reads are independent and
  side-effect free), and
* it keeps the frames in memory, so the forecast, the scoring pass and
  the calendar all work on the SAME frame instead of each downloading the
  history again.

WHAT IS AND IS NOT CACHED
-------------------------
The cache holds the RAW frames as they came out of storage. It is
keyed by (layer, symbol) and it EXPIRES, because the lakehouse changes:
the auto-refresh pass writes new bars into Silver and Gold every cycle,
and a frame cached before that write would be stale.

    20|The cache is invalidated explicitly by the writers - `invalidate` is
called by the pipeline after it rewrites a symbol - so a fresh frame
replaces a stale one IMMEDIATELY rather than waiting for the TTL. The
TTL is the backstop for the case where something else changed the
layer.

WHY THE CACHE IS NOT IN THE STORAGE BACKEND
-------------------------------------------
Because the storage backend is a thin, stateless adapter over MinIO or
the local filesystem. Policy about how long a frame may be reused, how
much memory the process may hold, and when a writer must push the
invalidation belongs one level up - in the service that decides.
Keeping it here means the policy can differ between the API (which
serves a user waiting for a page) and the batch (which wants the whole
universe in memory at once).

THE MEMORY BOUND IS DELIBERATE
------------------------------
    30|A cached frame is the symbol's daily bars plus the ~90 derived
indicator columns. Measured: ~3 MB per symbol. The default bound of 256
symbols is therefore ~750 MB, which is affordable on this host and
covers a whole browsing session.

The batch jobs, which want EVERY symbol at once, raise the bound
themselves rather than relying on a global default that would be either
too small for them or too large for the API.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Iterable

import pandas as pd

#: How many frames the cache may hold. See the module docstring for the
#: memory arithmetic behind the number.
DEFAULT_MAX_SYMBOLS = int(os.getenv("LAKEHOUSE_CACHE_SYMBOLS", "256"))

#: How long a frame may be reused before it is re-read, in seconds.
#:
#: WHY 300s: the auto-refresh pass rewrites a symbol's Silver and Gold
#: partitions roughly every 15 minutes, and it invalidates the cache
#: entry itself when it does. The TTL only covers the case where the
#: layer changed WITHOUT the writer telling anyone - and it has to be
#: long enough that a browsing session does not re-download the whole
#: history of every symbol it looks at, and short enough that a change
#: made by another process shows up.
DEFAULT_TTL_SECONDS = int(os.getenv("LAKEHOUSE_CACHE_TTL", "300"))


class FrameCache:
    """A TTL-bounded, explicitly invalidatable cache of lakehouse frames."""

    def __init__(self, max_symbols: int = DEFAULT_MAX_SYMBOLS, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._max_symbols = max(1, max_symbols)
        self._ttl_seconds = max(1, ttl_seconds)
        # key -> (stored_at, frame)
        self._store: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    # ------------------------------------------------------------------ core

    def get(self, layer: str, symbol: str) -> pd.DataFrame | None:
        """The cached frame for a symbol, or None when there is none."""
        key = (layer, symbol.upper())
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            stored_at, frame = entry
            if time.monotonic() - stored_at > self._ttl_seconds:
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
            return frame

    def put(self, layer: str, symbol: str, frame: pd.DataFrame) -> None:
        """Store a frame for a symbol."""
        key = (layer, symbol.upper())
        with self._lock:
            if key not in self._store and len(self._store) >= self._max_symbols:
                oldest = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                del self._store[oldest]
            self._store[key] = (time.monotonic(), frame)

    def invalidate(self, layer: str, symbol: str) -> None:
        """Drop one symbol's frame."""
        with self._lock:
            self._store.pop((layer, symbol.upper()), None)

    def clear(self, layer: str | None = None) -> None:
        """Drop every frame, or every frame of one layer."""
        with self._lock:
            if layer is None:
                self._store.clear()
                return
            for key in [k for k in self._store if k[0] == layer]:
                del self._store[key]

    def resize(self, max_symbols: int) -> None:
        """Change the bound, evicting the oldest entries if needed."""
        with self._lock:
            self._max_symbols = max(1, max_symbols)
            while len(self._store) > self._max_symbols:
                oldest = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                del self._store[oldest]

    @property
    def max_symbols(self) -> int:
        """The current bound on the number of cached frames."""
        with self._lock:
            return self._max_symbols

    def stats(self) -> dict[str, Any]:
        """What the cache is holding - used by the System Status page."""
        with self._lock:
            return {
                "entries": len(self._store),
                "max_symbols": self._max_symbols,
                "ttl_seconds": self._ttl_seconds,
                "hits": self.hits,
                "misses": self.misses,
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


#: The process-wide cache. Every layer of the application shares it, so
#: a frame read by the forecast pass is reused by the scoring pass.
GLOBAL_CACHE = FrameCache()


def get_cached(layer: str, symbol: str) -> pd.DataFrame | None:
    """The cached frame for a symbol, or None."""
    return GLOBAL_CACHE.get(layer, symbol)


def put_cached(layer: str, symbol: str, frame: pd.DataFrame) -> None:
    """Store a frame for a symbol."""
    GLOBAL_CACHE.put(layer, symbol, frame)


def invalidate_cached(layer: str, symbol: str) -> None:
    """Drop one symbol's cached frame."""
    GLOBAL_CACHE.invalidate(layer, symbol)


def clear_cached(layer: str | None = None) -> None:
    """Drop cached frames."""
    GLOBAL_CACHE.clear(layer)


def cached_read(layer: str, symbol: str, reader) -> pd.DataFrame:
    """Read a symbol through the cache.

    ``reader`` is called with the symbol and must return the frame. The
    frame is stored on a miss and returned as-is on a hit.

    The frame is returned WITHOUT a copy, so callers must treat it as
    read-only. Every caller in this project does.
    """
    cached = GLOBAL_CACHE.get(layer, symbol)
    if cached is not None:
        return cached
    frame = reader(symbol)
    if frame is not None and not frame.empty:
        GLOBAL_CACHE.put(layer, symbol, frame)
    return frame


def warm_cache(layer: str, symbols: Iterable[str], reader, workers: int = 8) -> dict[str, int]:
    """Read many symbols into the cache CONCURRENTLY.

    WHY CONCURRENTLY: the reads are independent network round-trips to
    MinIO, so they overlap almost perfectly - the pass is latency-bound,
    not CPU-bound. Reading 973 symbols in 8 threads cuts the read time
    from ~8 minutes to ~1 minute.

    The result is a cache that holds every symbol the batch needs, so
    the forecast pass, the scoring pass and the calendar all read from
    memory instead of going back to storage.

    Returns a summary of what was warmed and how it went.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    target = [symbol.upper() for symbol in symbols]
    if not target:
        return {"requested": 0, "cached": 0, "failed": 0}

    # The frames already in the cache are not re-read.
    pending = [symbol for symbol in target if GLOBAL_CACHE.get(layer, symbol) is None]
    failed = 0

    if pending:
        pool_size = max(1, min(workers, len(pending)))
        with ThreadPoolExecutor(max_workers=pool_size) as pool:
            futures = {
                pool.submit(reader, symbol): symbol for symbol in pending
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    frame = future.result()
                except Exception:  # noqa: BLE001 - one bad symbol must not stop the batch
                    failed += 1
                    continue
                if frame is not None and not frame.empty:
                    GLOBAL_CACHE.put(layer, symbol, frame)

    return {
        "requested": len(target),
        "read": len(pending),
        "cached": len(target) - failed,
        "failed": failed,
    }
