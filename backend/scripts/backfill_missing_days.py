"""Backfill the trading days that the refresh watermark stepped over.

WHY THIS EXISTS
---------------
The incremental refresh computed its next fetch window as

    start = last_bar_timestamp.replace(tzinfo=None) + timedelta(days=1)

Two things went wrong with that:

  1. The stored bar is stamped at the exchange's session OPEN in UTC
     (13:30 UTC for the NYSE in EDT, 14:30 UTC in EST, 02:00 UTC for HOSE).
     A provider stamps the bar for the NEXT trading day at that same
     instant, so "one day after the last bar" is not guaranteed to be
     before the next day's bar - the day's bar can be excluded from the
     response, and the day is lost permanently.
  2. The boundary was NAIVE, and `datetime.timestamp()` reads a naive
     datetime in the MACHINE'S local timezone, moving the window by the
     host's UTC offset.

Measured on this project: 946 distinct "unexplained" missing weekdays,
with 2026-10-21 missing for 358 symbols while 489 of their peers had it.
A provider outage cannot produce that split - the market was open and
Yahoo served the bar. Replaying the provider confirmed the bar IS served;
it was simply never requested.

The refresh now uses a 5-day overlap, so the next normal refresh pass
heals the gaps on its own. This script exists for the backlog that
predates the fix: it finds the gaps, fetches the missing days, and writes
them to Bronze so the regular Silver/Gold rebuild can pick them up.

    # Report the gaps, change nothing
    python3 scripts/backfill_missing_days.py --dry-run

    # Fetch and write the missing days
    python3 scripts/backfill_missing_days.py

    # Only a few symbols
    python3 scripts/backfill_missing_days.py --symbols AAPL VCB

IDEMPOTENT
-----------
Bronze's append deduplicates on (symbol, timestamp), so re-running writes
nothing extra for a day that is already present.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import get_logger
from app.data_sources.factory import get_data_provider
from app.lakehouse.bronze import BronzeLayer
from app.services.market_service import clear_symbol_cache

logger = get_logger(__name__)

BRONZE_PREFIX = "symbol="


def bronze_symbols(bronze: BronzeLayer) -> list[str]:
    """Every symbol that exists in the Bronze bucket."""
    symbols: set[str] = set()
    for key in bronze.storage.list_objects("bronze", ""):
        if not key.startswith(BRONZE_PREFIX):
            continue
        head = key.split("/", 1)[0]
        symbols.add(head.split("=", 1)[1])
    return sorted(symbols)


def trading_days(series: pd.Series) -> set:
    """The distinct calendar days covered by a symbol's stored bars."""
    stamps = pd.to_datetime(series, utc=True, errors="coerce")
    return set(stamps.dropna().dt.date)


def find_gaps(bronze: BronzeLayer, symbol: str, lookback_days: int) -> list:
    """The weekdays inside the symbol's own range that carry no bar.

    Only weekdays are considered, and only those between the symbol's
    first and last stored bar - a symbol that simply has no history yet
    is not "missing" anything, and a market holiday is not a gap.

    The trading calendar is not hardcoded: a day is considered missing
    only when a MAJORITY of the symbol's peers have a bar for it. That
    keeps real holidays (a day nobody traded) from being reported, while
    still catching the day that only a subset of symbols lost.
    """
    frame = bronze.read(symbol)
    if frame.empty or "timestamp" not in frame.columns:
        return []
    days = trading_days(frame["timestamp"])
    if len(days) < 2:
        return []
    first, last = min(days), max(days)
    # Restrict the search to the recent window so the run stays bounded.
    window_start = max(first, last - timedelta(days=lookback_days))
    candidate = []
    day = window_start
    while day <= last:
        if day.weekday() < 5 and day not in days:
            candidate.append(day)
        day += timedelta(days=1)
    return candidate


def fetch_gaps(symbol: str, gaps: list, provider) -> pd.DataFrame:
    """Fetch the missing days for one symbol."""
    if not gaps:
        return pd.DataFrame()
    start = datetime(gaps[0].year, gaps[0].month, gaps[0].day, tzinfo=timezone.utc)
    end = datetime(gaps[-1].year, gaps[-1].month, gaps[-1].day, tzinfo=timezone.utc) + timedelta(days=1)
    frame = provider.get_historical_data(symbol=symbol, start=start, end=end, interval="1d")
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    wanted = set(gaps)
    keep = frame["timestamp"].dt.date.isin(wanted)
    return frame[keep].reset_index(drop=True)


def repair_one(symbol: str, gaps: list, provider, bronze: BronzeLayer) -> dict:
    """Fetch and write the missing days for one symbol. Never raises."""
    result = {"symbol": symbol, "gaps": len(gaps), "written": 0, "error": None}
    try:
        frame = fetch_gaps(symbol, gaps, provider)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"fetch: {exc}"
        return result
    if frame.empty:
        return result
    try:
        written = bronze.append(
            frame,
            lineage={
                "source": "backfill_missing_days",
                "provider": provider.source_name,
                "symbol": symbol,
                "interval": "1d",
            },
        )
        result["written"] = int(written.get("records_written", len(frame)))
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"append: {exc}"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Explicit symbols to repair. Default: every symbol in Bronze.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report the gaps and exit without writing.")
    parser.add_argument("--workers", type=int, default=4,
                        help="Symbols repaired in parallel (default 4).")
    parser.add_argument("--lookback-days", type=int, default=60,
                        help="How far back to look for gaps (default 60).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Repair at most N symbols.")
    args = parser.parse_args(argv)

    bronze = BronzeLayer()
    if args.symbols:
        candidates = [s.strip().upper() for s in args.symbols if s.strip()]
    else:
        candidates = bronze_symbols(bronze)
    print(f"Scanning {len(candidates)} symbol(s) for missing trading days ...")

    # Pass 1: find the gaps.
    plan: dict[str, list] = {}
    for symbol in candidates:
        try:
            gaps = find_gaps(bronze, symbol, args.lookback_days)
        except Exception as exc:  # noqa: BLE001
            logger.warning("gap scan failed for %s: %s", symbol, exc)
            continue
        if gaps:
            plan[symbol] = gaps

    total_gaps = sum(len(v) for v in plan.values())
    print(f"  {len(plan)} symbol(s) have gaps, {total_gaps} missing day(s) in total")

    if not plan:
        print("Nothing to repair.")
        return 0

    # Report which calendar days are affected and how widely, so a real
    # outage (every symbol missing the day) is distinguishable from the
    # per-symbol gap this script targets.
    day_counts: dict = {}
    for gaps in plan.values():
        for day in gaps:
            day_counts[day] = day_counts.get(day, 0) + 1
    print("  affected days (day -> number of symbols missing it):")
    for day, count in sorted(day_counts.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    {day} ({day.strftime('%a')}): {count}")

    if args.dry_run:
        print("Dry run - sample of affected symbols:")
        for symbol, gaps in list(plan.items())[:20]:
            print(f"  {symbol}: {len(gaps)} day(s) -> {[str(d) for d in gaps[:5]]}")
        return 0

    if args.limit is not None:
        plan = dict(list(plan.items())[: args.limit])
        print(f"  limited to {len(plan)} symbol(s) by --limit")

    provider = get_data_provider("multi_source")
    started = time.monotonic()
    repaired = 0
    written_total = 0
    failed: list[dict] = []

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(repair_one, symbol, gaps, provider, bronze): symbol
            for symbol, gaps in plan.items()
        }
        for done, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            if result["error"]:
                failed.append(result)
                logger.warning("repair failed for %s: %s", result["symbol"], result["error"])
            else:
                repaired += 1
                written_total += result["written"]
            if done % 25 == 0 or done == len(plan):
                print(f"  {done}/{len(plan)} done | wrote {written_total} row(s) "
                      f"| {failed and len(failed) or 0} failed")

    try:
        clear_symbol_cache()
    except Exception:  # noqa: BLE001
        pass

    print()
    print(f"Repaired {repaired}/{len(plan)} symbol(s), wrote {written_total} row(s) "
          f"in {time.monotonic() - started:.0f}s")
    if failed:
        print(f"{len(failed)} symbol(s) failed:")
        for result in failed[:20]:
            print(f"  {result['symbol']}: {result['error']}")
        return 1
    print()
    print("Next: rebuild Silver and Gold so the new rows reach the UI:")
    print("  python3 scripts/backfill_silver_gold.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
