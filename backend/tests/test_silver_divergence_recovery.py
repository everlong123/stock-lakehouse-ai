"""Silver/Gold must converge to Bronze even when Bronze stops changing.

WHY THIS FILE EXISTS
--------------------
A daily bar is stamped at the session OPEN, and the provider serves the price
as of the last fetch. So a refresh that runs WHILE the market is still open
stores a mid-session snapshot, and Silver/Gold are rebuilt from it.

The provider then settles that same bar with the closing price. The next
refresh overwrites the Bronze row - same (symbol, timestamp), different
close - and reports ``updated_records = 1``, so Silver/Gold are rebuilt and
converge. That path already works (see
``tests/test_restatement_propagation.py``).

It stops working when the Bronze write lands but the Silver/Gold rebuild
does NOT happen:

  * the process is killed between the Bronze write and the Gold write,
  * the rebuild is skipped because the machine ran out of memory,
  * another writer (an ingest script, the API) updates Bronze directly.

Bronze then holds the SETTLED close while Silver and Gold keep the
MID-SESSION snapshot. From that moment the divergence is invisible to every
other rebuild trigger:

  * ``new_records = 0`` - the partition did not grow,
  * ``updated_records = 0`` - Bronze already held the settled value, so the
    provider "restated" nothing,
  * the trading-day watermark guard compares EQUAL, because both layers
    carry the SAME session date.

Silver/Gold are therefore never rebuilt and the stale close is served to the
web FOREVER.

MEASURED ON 2026-11-12
----------------------
78 symbols were stuck this way. ``0001.HK`` served close 68.95 (the 07:28
mid-session snapshot) while Bronze held 69.35 (the settled close) - a 0.58%
gap on the newest bar, and the symbol could not recover on its own.

THE FIX
-------
``auto_refresh._silver_diverged_from_bronze`` compares the newest close of
Bronze against the newest close of Silver and triggers the rebuild when they
disagree.

Run from the backend directory:

    .venv/Scripts/python.exe tests/test_silver_divergence_recovery.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.services.auto_refresh import (  # noqa: E402
    _closes_differ,
    _newest_session_close,
    _silver_diverged_from_bronze,
)

FAILURES: list[str] = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"  [ OK ] {name}")
    else:
        print(f"  [FAIL] {name}")
        FAILURES.append(name)


def _bar(day: str, close: float, stamp: str = "01:30:00") -> dict:
    return {
        "symbol": "0001.HK",
        "timestamp": pd.Timestamp(f"{day} {stamp}", tz="UTC"),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1000.0,
    }


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class _FakeLayer:
    """A layer stub that returns a fixed newest-session close."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def newest_session_close(self, symbol: str):
        from app.lakehouse.session import newest_bar_session_close

        return newest_bar_session_close(self._frame)


def main() -> int:
    print("silver divergence recovery")

    # ── 1. The newest-session helper ─────────────────────────────────────
    day, close = _newest_session_close(_frame([_bar("2026-11-11", 72.10),
                                                _bar("2026-11-12", 69.35)]))
    check("the newest session date is found", str(day) == "2026-11-12")
    check("the newest close is found", close == 69.35)
    check("an empty frame yields no session", _newest_session_close(pd.DataFrame()) == (None, None))

    # ── 2. The tolerance helper ──────────────────────────────────────────
    check("identical closes do not differ", not _closes_differ(69.35, 69.35))
    check("different closes differ", _closes_differ(68.95, 69.35))
    check("float noise does not differ", not _closes_differ(69.35, 69.350000001))
    check("a missing close never differs", not _closes_differ(None, 69.35))

    # ── 3. The divergence probe: the exact measured case ─────────────────
    # Bronze holds the settled close 69.35; Silver holds the mid-session
    # snapshot 68.95 for the SAME session date.
    bronze = _FakeLayer(_frame([_bar("2026-11-11", 72.10), _bar("2026-11-12", 69.35)]))
    silver_stale = _FakeLayer(_frame([_bar("2026-11-11", 72.10), _bar("2026-11-12", 68.95)]))
    check(
        "Bronze settled vs Silver mid-session is detected as diverged",
        _silver_diverged_from_bronze("0001.HK", bronze, silver_stale),
    )

    # ── 4. The probe stays quiet when the layers agree ───────────────────
    silver_ok = _FakeLayer(_frame([_bar("2026-11-11", 72.10), _bar("2026-11-12", 69.35)]))
    check(
        "identical layers are not reported as diverged",
        not _silver_diverged_from_bronze("0001.HK", bronze, silver_ok),
    )

    # ── 5. A session-day lag is NOT this probe's job ─────────────────────
    # The trading-day watermark guard already handles it, and reporting it
    # here would make the two guards overlap.
    silver_older = _FakeLayer(_frame([_bar("2026-11-11", 72.10)]))
    check(
        "a Silver that lags by a whole session is left to the watermark guard",
        not _silver_diverged_from_bronze("0001.HK", bronze, silver_older),
    )

    # ── 6. An empty Silver is a divergence (nothing to serve) ────────────
    check(
        "an empty Silver is reported as diverged",
        _silver_diverged_from_bronze("0001.HK", bronze, _FakeLayer(pd.DataFrame())),
    )

    # ── 7. The refresh actually CALLS the probe ──────────────────────────
    source = Path(sys.modules["app.services.auto_refresh"].__file__).read_text(
        encoding="utf-8"
    )
    check(
        "the auto-refresh calls the divergence probe",
        "_silver_diverged_from_bronze(" in source,
    )
    check(
        "the auto-refresh rebuilds when Silver disagrees with Bronze",
        "Silver disagrees with Bronze on the" in source,
    )

    # ── 8. The Bronze append CANNOT detect this case on its own ──────────
    # This is why the fix has to live in the refresh decision and not in
    # Bronze: by the time the refresh runs, Bronze already holds the settled
    # value, so the append reports no change at all.
    from app.lakehouse.bronze import _count_restated_rows

    bronze_frame = _frame([_bar("2026-11-11", 72.10), _bar("2026-11-12", 69.35)])
    silver_frame = _frame([_bar("2026-11-11", 72.10), _bar("2026-11-12", 68.95)])
    check(
        "Bronze vs itself reports no restatement (so the probe is required)",
        _count_restated_rows(bronze_frame, bronze_frame) == 0,
    )
    check(
        "Silver vs Bronze reports the difference",
        _count_restated_rows(silver_frame, bronze_frame) == 1,
    )

    # ── 9. The probe reads only the NEWEST partition ────────────────────
    # A full read() pulls every monthly partition (~120 objects for a
    # 10-year daily ticker). Doing that for two layers on every symbol of
    # every pass is exactly what made the refresh crawl, so the probe has to
    # use the lightweight readers.
    bronze_source = Path(sys.modules["app.lakehouse.bronze"].__file__).read_text(
        encoding="utf-8"
    )
    silver_source = Path(sys.modules["app.lakehouse.silver"].__file__).read_text(
        encoding="utf-8"
    )
    check(
        "Bronze exposes a newest_session_close reader",
        "def newest_session_close" in bronze_source,
    )
    check(
        "Silver exposes a newest_session_close reader",
        "def newest_session_close" in silver_source,
    )
    check(
        "the probe uses the lightweight readers, not a full read",
        "newest_session_close(symbol)" in source
        and "bronze.read(sym)" not in source
        and "silver.read(symbol)" not in source,
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
