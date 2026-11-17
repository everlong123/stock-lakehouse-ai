"""A provider RESTATEMENT must be detected and must trigger a Silver/Gold rebuild.

WHY THIS FILE EXISTS
--------------------
Providers revise history. Yahoo re-published ``ADS.DE`` 2026-11-03 with a
close of 168.10 after having served 168.85 the day before.

Bronze picked the revision up - its dedupe keeps the freshly fetched row for
the same ``(symbol, timestamp)``. But the revision did NOT grow the partition:
the bar count was identical before and after. The auto-refresh decided what to
do from ``new_records`` alone, i.e. from the partition's GROWTH, so it read
"nothing new for this symbol" and skipped the Silver/Gold rebuild.

Silver and Gold therefore kept 168.85, the web served 168.85, and the value
stayed wrong forever. Re-fetching did not help, because the problem was never
the fetch - it was that a CONTENT change was mistaken for a NO-OP.

These tests pin down the three fixes:

1. ``BronzeLayer.append`` reports ``updated_records`` - the rows the provider
   restated - separately from ``new_records`` (the rows that are new).
2. The auto-refresh rebuilds Silver/Gold when ``updated_rows > 0``, not only
   when ``new_rows > 0``.
3. ``reingest_window.py`` compares Bronze, Silver AND Gold against the
   provider, so a symbol whose Bronze is already correct but whose Silver and
   Gold lag behind is still rebuilt.

Run from the backend directory:

    .venv/Scripts/python.exe tests/test_restatement_propagation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.lakehouse.bronze import _count_restated_rows  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"  [ OK ] {name}")
    else:
        print(f"  [FAIL] {name}")
        FAILURES.append(name)


def _bar(day: str, close: float, open_: float | None = None,
         high: float | None = None, low: float | None = None,
         volume: float = 1000.0) -> dict:
    open_ = close if open_ is None else open_
    high = max(close, open_) if high is None else high
    low = min(close, open_) if low is None else low
    return {
        "symbol": "ADS.DE",
        "timestamp": pd.Timestamp(f"{day} 08:00:00", tz="UTC"),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def main() -> int:
    print("restatement propagation")

    # ── 1. A revised close is counted as a restatement ────────────────────
    stored = _frame([_bar("2026-11-03", 168.85, 167.70, 171.55, 167.35)])
    revised = _frame([_bar("2026-11-03", 168.10, 167.70, 171.55, 167.35)])
    check(
        "a revised close is counted as a restatement",
        _count_restated_rows(stored, revised) == 1,
    )

    # ── 2. An identical bar is NOT a restatement ──────────────────────────
    check(
        "an identical bar is not a restatement",
        _count_restated_rows(stored, stored) == 0,
    )

    # ── 3. A genuinely new bar is not a restatement ───────────────────────
    new_bar = _frame([_bar("2026-11-04", 168.60)])
    check(
        "a bar for a new session is not a restatement",
        _count_restated_rows(stored, new_bar) == 0,
    )

    # ── 4. Float noise does not count as a restatement ────────────────────
    # Only the close moves, and only by a rounding error. The OHLC fields
    # stay identical, otherwise this would be a genuine restatement.
    noisy = _frame([_bar("2026-11-03", 168.850000001, 167.70, 171.55, 167.35)])
    check(
        "float rounding noise is not a restatement",
        _count_restated_rows(stored, noisy) == 0,
    )

    # ── 5. A revised OPEN counts too, not just the close ──────────────────
    open_revised = _frame([_bar("2026-11-03", 168.85, 167.60, 171.55, 167.35)])
    check(
        "a revised open is counted as a restatement",
        _count_restated_rows(stored, open_revised) == 1,
    )

    # ── 6. A volume-only revision is not a price restatement ──────────────
    # The bar's CONTENT is unchanged; only turnover moved. That is a data
    # nuance, not a price correction, and it must not force a rebuild.
    volume_only = _frame([_bar("2026-11-03", 168.85, 167.70, 171.55, 167.35,
                               volume=9999.0)])
    check(
        "a volume-only revision is not a price restatement",
        _count_restated_rows(stored, volume_only) == 0,
    )

    # ── 7. Duplicated keys do not inflate the count ───────────────────────
    duplicated = _frame([
        _bar("2026-11-03", 168.10, 167.70, 171.55, 167.35),
        _bar("2026-11-03", 168.10, 167.70, 171.55, 167.35),
    ])
    check(
        "a duplicated incoming row counts once, not twice",
        _count_restated_rows(stored, duplicated) == 1,
    )

    # ── 8. The real-world case, exactly as measured ───────────────────────
    # Bronze already held the revised value; Silver and Gold still held the
    # old one. The re-ingest script compared Bronze only, found no
    # difference, and skipped the rebuild.
    bronze_current = _frame([_bar("2026-11-03", 168.10, 167.70, 171.55, 167.35)])
    silver_stale = _frame([_bar("2026-11-03", 168.85, 167.70, 171.55, 167.35)])
    check(
        "Bronze (current) vs provider (current) is clean",
        _count_restated_rows(bronze_current, bronze_current) == 0,
    )
    check(
        "Silver (stale) vs provider (current) is detected as a restatement",
        _count_restated_rows(silver_stale, bronze_current) == 1,
    )

    # ── 9. The auto-refresh rebuild trigger ───────────────────────────────
    # The rebuild must fire on a restatement, not only on new rows.
    import app.services.auto_refresh as auto_refresh

    source = Path(auto_refresh.__file__).read_text(encoding="utf-8")
    check(
        "the auto-refresh reads updated_rows from the Bronze metadata",
        'meta.get("updated_records", 0)' in source,
    )
    check(
        "the auto-refresh rebuilds when a row was restated",
        'res.get("updated_rows", 0) > 0' in source,
    )

    # ── 10. The re-ingest script compares every layer ─────────────────────
    script = Path(__file__).resolve().parents[1] / "scripts" / "reingest_window.py"
    script_source = script.read_text(encoding="utf-8")
    check(
        "the re-ingest script reads Silver and Gold, not just Bronze",
        "SilverLayer" in script_source and "GoldLayer" in script_source,
    )
    check(
        "the re-ingest script invalidates the API cache with POST",
        'method="POST"' in script_source,
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
