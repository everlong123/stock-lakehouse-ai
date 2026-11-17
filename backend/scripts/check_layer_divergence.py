"""Detect symbols whose Silver/Gold CONTENT disagrees with Bronze.

WHY THIS EXISTS
---------------
The auto-refresh used to decide whether to rebuild Silver/Gold from the
partition's GROWTH (`new_records`). A provider restatement - the same bar
with a revised close - does not grow the partition, so it was invisible: the
refresh skipped the rebuild and Silver/Gold kept the pre-revision value
forever. The watermark check that runs when nothing was appended compares only
the NEWEST bar, so a symbol whose OLDER rows were revised also looked "in
sync".

The result is a class of divergence that no amount of re-fetching fixes:
Bronze holds the provider's current value, Silver and Gold hold an older
one, and the web serves the older one.

This script compares the CONTENT of the three layers per symbol and reports
every symbol where they disagree, so the backlog can be measured and fixed.

Run from the backend directory:

    .venv/Scripts/python.exe scripts/check_layer_divergence.py
    .venv/Scripts/python.exe scripts/check_layer_divergence.py --days 90
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import get_logger, setup_logging  # noqa: E402
from app.lakehouse.bronze import BronzeLayer  # noqa: E402
from app.lakehouse.gold import GoldLayer  # noqa: E402
from app.lakehouse.silver import SilverLayer  # noqa: E402
from app.lakehouse.session import canonicalize_daily_sessions  # noqa: E402

logger = get_logger(__name__)

# Two prices count as equal when they agree to this relative tolerance.
# 1e-6 matches the verifier's default tolerance.
TOLERANCE = 1e-6


def bronze_symbols() -> list[str]:
    """Every symbol present in the Bronze bucket."""
    bronze = BronzeLayer()
    symbols: set[str] = set()
    for key in bronze.storage.list_objects("bronze", ""):
        if not key.startswith("symbol="):
            continue
        head = key.split("/", 1)[0]
        symbols.add(head.split("=", 1)[1])
    return sorted(symbols)


def _session_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Reduce a frame to one row per trading day, keyed by the day.

    The rows are CANONICALISED first, because Bronze holds the raw provider
    output while Silver and Gold hold one bar per trading day. A day that
    arrives as several intraday ticks (VTI 2026-10-26 arrives at 13:30 and
    again at 16:56) is one session, and comparing Bronze's raw ticks against
    Silver's single canonical bar would report a divergence on every such day
    for every symbol - noise, not a defect.
    """
    if frame.empty or "timestamp" not in frame.columns:
        return pd.DataFrame()
    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
    working = working.dropna(subset=["timestamp"])
    if working.empty:
        return pd.DataFrame()
    try:
        working, _report = canonicalize_daily_sessions(working)
    except Exception:  # noqa: BLE001 - fall back to the raw rows
        pass
    working["_day"] = working["timestamp"].dt.strftime("%Y-%m-%d")
    return working


def compare(stored: pd.DataFrame, source: pd.DataFrame, days: int) -> list[dict]:
    """Sessions where ``stored`` and ``source`` disagree on the close."""
    a = _session_index(stored)
    b = _session_index(source)
    if a.empty or b.empty:
        return []

    if days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        a = a[a["_day"] >= cutoff]
        b = b[b["_day"] >= cutoff]
        if a.empty or b.empty:
            return []

    a = a.drop_duplicates(subset=["_day"], keep="last")
    b = b.drop_duplicates(subset=["_day"], keep="last")

    merged = a[["_day", "close"]].merge(
        b[["_day", "close"]], on="_day", how="inner", suffixes=("_stored", "_source")
    )
    if merged.empty:
        return []

    stored_close = pd.to_numeric(merged["close_stored"], errors="coerce")
    source_close = pd.to_numeric(merged["close_source"], errors="coerce")
    diff = (stored_close - source_close).abs()
    scale = source_close.abs().clip(lower=1e-9)
    differing = merged[(diff / scale) > TOLERANCE]

    findings: list[dict] = []
    for _, row in differing.iterrows():
        findings.append(
            {
                "day": row["_day"],
                "stored": float(row["close_stored"]),
                "source": float(row["close_source"]),
                "rel": float(diff.loc[row.name] / scale.loc[row.name]),
            }
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90,
                        help="Only compare the trailing N days (0 = all history)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after N symbols (0 = no limit)")
    args = parser.parse_args(argv)

    setup_logging()

    symbols = bronze_symbols()
    if args.limit:
        symbols = symbols[: args.limit]
    print(f"Comparing Bronze vs Silver vs Gold for {len(symbols)} symbol(s) "
          f"(trailing {args.days or 'all'} days)")
    print()

    bronze = BronzeLayer()
    silver = SilverLayer()
    gold = GoldLayer()

    divergent: list[dict] = []
    errors = 0
    for index, symbol in enumerate(symbols, start=1):
        try:
            b = bronze.read(symbol)
            s = silver.read(symbol)
            g = gold.read(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("read failed for %s: %s", symbol, exc)
            errors += 1
            continue

        silver_diff = compare(s, b, args.days)
        gold_diff = compare(g, b, args.days)
        if silver_diff or gold_diff:
            divergent.append(
                {
                    "symbol": symbol,
                    "silver": silver_diff,
                    "gold": gold_diff,
                }
            )
        if index % 100 == 0:
            print(f"  {index}/{len(symbols)} checked, {len(divergent)} divergent so far")

    print()
    print("=" * 78)
    print(f"symbols checked        : {len(symbols)}")
    print(f"symbols with divergence: {len(divergent)}")
    print(f"read errors            : {errors}")
    print("=" * 78)

    if divergent:
        print()
        print("DIVERGENT SYMBOLS (Silver/Gold disagree with Bronze):")
        for entry in divergent:
            sessions = sorted({d["day"] for d in entry["silver"] + entry["gold"]})
            print(f"  {entry['symbol']:<12} {len(sessions)} session(s): "
                  f"{', '.join(sessions[-6:])}{' ...' if len(sessions) > 6 else ''}")
        print()
        print("Fix with a forced rebuild (the watermark check cannot see this):")
        print("    python scripts/backfill_silver_gold.py --symbols <SYM> --force")
        return 1

    print()
    print("VERDICT: every symbol's Silver and Gold agree with Bronze.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
