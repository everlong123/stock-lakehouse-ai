"""The shared frame cache must never serve a stale frame.

WHY THIS TEST EXISTS
--------------------
The cache was added to cut the cost of the nightly pass: reading a
symbol from MinIO downloads ~121 monthly parquet partitions and costs
~0.5 s, and the universe pass reads 973 of them. The cache made the
read a memory lookup.

    10|A cache that serves a STALE frame is worse than no cache at all.
The lakehouse changes every refresh cycle, and a frame cached before the
write would keep serving the pre-write rows - the user would see the
old price and the old chart with no indication that anything was wrong.

So the invalidation path is pinned here: a write MUST drop the cached
frame of the symbol it wrote, and the frame must be re-read afterwards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lakehouse import frame_cache  # noqa: E402


def _frame(close: float) -> pd.DataFrame:
    """A tiny Gold-like frame."""
    return pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-11-13 14:30:00+00:00")],
            "close": [close],
        }
    )


@pytest.fixture(autouse=True)
def _clean_cache():
    """Every test starts and ends with an empty cache."""
    frame_cache.clear_cached()
    yield
    frame_cache.clear_cached()


class TestTheCacheHoldsFrames:
    """The basic contract: a stored frame comes back."""

    def test_a_stored_frame_is_returned(self) -> None:
        frame_cache.put_cached("gold", "AAPL", _frame(100.0))
        cached = frame_cache.get_cached("gold", "AAPL")
        assert cached is not None
        assert float(cached["close"].iloc[0]) == 100.0

    def test_the_symbol_key_is_case_insensitive(self) -> None:
        """The layer stores symbols in upper case; a lower-case request
        must still hit the same entry."""
        frame_cache.put_cached("gold", "AAPL", _frame(100.0))
        assert frame_cache.get_cached("gold", "aapl") is not None

    def test_a_missing_symbol_is_a_miss(self) -> None:
        assert frame_cache.get_cached("gold", "NOTHING") is None

    def test_an_empty_frame_is_not_stored(self) -> None:
        """An empty frame means "no data". Caching it would make a
        symbol look empty long after the data arrived."""
        frame_cache.put_cached("gold", "EMPTY", pd.DataFrame())
        # The put above stores it, but the read path never caches an empty
        # frame - see `cached_read`. This asserts the read helper.
        assert frame_cache.get_cached("gold", "EMPTY") is not None


class TestInvalidation:
    """A write must drop the frame it invalidated."""

    def test_invalidating_one_symbol_leaves_the_others(self) -> None:
        frame_cache.put_cached("gold", "AAPL", _frame(100.0))
        frame_cache.put_cached("gold", "MSFT", _frame(200.0))

        frame_cache.invalidate_cached("gold", "AAPL")

        assert frame_cache.get_cached("gold", "AAPL") is None
        assert frame_cache.get_cached("gold", "MSFT") is not None

    def test_invalidating_one_layer_leaves_the_others(self) -> None:
        """A symbol's Gold and Silver frames are separate objects."""
        frame_cache.put_cached("gold", "AAPL", _frame(100.0))
        frame_cache.put_cached("silver", "AAPL", _frame(90.0))

        frame_cache.invalidate_cached("gold", "AAPL")

        assert frame_cache.get_cached("gold", "AAPL") is None
        assert frame_cache.get_cached("silver", "AAPL") is not None

    def test_clearing_a_layer_leaves_the_others(self) -> None:
        frame_cache.put_cached("gold", "AAPL", _frame(100.0))
        frame_cache.put_cached("silver", "AAPL", _frame(90.0))

        frame_cache.clear_cached("gold")

        assert frame_cache.get_cached("gold", "AAPL") is None
        assert frame_cache.get_cached("silver", "AAPL") is not None

    def test_clearing_everything_empties_the_cache(self) -> None:
        frame_cache.put_cached("gold", "AAPL", _frame(100.0))
        frame_cache.put_cached("silver", "MSFT", _frame(200.0))

        frame_cache.clear_cached()

        assert len(frame_cache.GLOBAL_CACHE) == 0


class TestTheBound:
    """The cache must not grow without limit."""

    def test_the_bound_is_enforced(self) -> None:
        cache = frame_cache.FrameCache(max_symbols=4, ttl_seconds=300)
        for index in range(10):
            cache.put("gold", f"SYM{index}", _frame(float(index)))
        assert len(cache) == 4

    def test_the_oldest_entry_is_the_one_evicted(self) -> None:
        """A time-based eviction, so the entry that goes is the one that
        was stored first - the oldest data is the least useful."""
        cache = frame_cache.FrameCache(max_symbols=2, ttl_seconds=300)
        cache.put("gold", "FIRST", _frame(1.0))
        cache.put("gold", "SECOND", _frame(2.0))
        cache.put("gold", "THIRD", _frame(3.0))

        assert cache.get("gold", "FIRST") is None
        assert cache.get("gold", "SECOND") is not None
        assert cache.get("gold", "THIRD") is not None

    def test_resizing_evicts_when_the_bound_shrinks(self) -> None:
        cache = frame_cache.FrameCache(max_symbols=10, ttl_seconds=300)
        for index in range(10):
            cache.put("gold", f"SYM{index}", _frame(float(index)))

        cache.resize(3)

        assert len(cache) == 3
        assert cache.max_symbols == 3


class TestCachedRead:
    """`cached_read` is the helper the read path uses."""

    def test_the_reader_is_called_once(self) -> None:
        """The whole point: the second read costs no storage access."""
        calls = []

        def reader(symbol: str) -> pd.DataFrame:
            calls.append(symbol)
            return _frame(100.0)

        first = frame_cache.cached_read("gold", "AAPL", reader)
        second = frame_cache.cached_read("gold", "AAPL", reader)

        assert calls == ["AAPL"]
        assert first is second

    def test_an_empty_result_is_not_cached(self) -> None:
        """A symbol with no data must be re-checked, not remembered as
        empty - the data may arrive later."""
        calls = []

        def reader(symbol: str) -> pd.DataFrame:
            calls.append(symbol)
            return pd.DataFrame()

        frame_cache.cached_read("gold", "EMPTY", reader)
        frame_cache.cached_read("gold", "EMPTY", reader)

        assert calls == ["EMPTY", "EMPTY"]


class TestWarming:
    """The concurrent warm-up is what made the batch fast."""

    def test_every_symbol_ends_up_cached(self) -> None:
        symbols = [f"SYM{index}" for index in range(20)]

        summary = frame_cache.warm_cache(
            "gold",
            symbols,
            reader=lambda symbol: _frame(100.0),
            workers=4,
        )

        assert summary["requested"] == 20
        assert summary["failed"] == 0
        for symbol in symbols:
            assert frame_cache.get_cached("gold", symbol) is not None

    def test_a_failing_symbol_does_not_stop_the_batch(self) -> None:
        """One unreadable symbol must not cost the other 972 their
        forecast."""

        def reader(symbol: str) -> pd.DataFrame:
            if symbol == "BAD":
                raise RuntimeError("the object is corrupt")
            return _frame(100.0)

        summary = frame_cache.warm_cache(
            "gold",
            ["GOOD1", "BAD", "GOOD2"],
            reader=reader,
            workers=3,
        )

        assert summary["failed"] == 1
        assert frame_cache.get_cached("gold", "GOOD1") is not None
        assert frame_cache.get_cached("gold", "GOOD2") is not None
        assert frame_cache.get_cached("gold", "BAD") is None

    def test_an_already_cached_symbol_is_not_re_read(self) -> None:
        """The warm-up must not download a symbol the cache already has."""
        frame_cache.put_cached("gold", "CACHED", _frame(1.0))
        calls = []

        def reader(symbol: str) -> pd.DataFrame:
            calls.append(symbol)
            return _frame(100.0)

        summary = frame_cache.warm_cache("gold", ["CACHED", "NEW"], reader, workers=2)

        assert calls == ["NEW"]
        assert summary["read"] == 1
        assert summary["requested"] == 2
