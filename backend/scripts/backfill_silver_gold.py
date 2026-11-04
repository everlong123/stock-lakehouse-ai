"""Rebuild Silver and Gold for every symbol whose Gold layer lags behind Bronze.

Run from the backend directory:

    # Report what is stale, change nothing
    .venv/Scripts/python.exe scripts/backfill_silver_gold.py --dry-run

    # Rebuild everything that is stale, 4 symbols in parallel
    .venv/Scripts/python.exe scripts/backfill_silver_gold.py

    # Only a few symbols
    .venv/Scripts/python.exe scripts/backfill_silver_gold.py --symbols AAPL MSFT NVDA

WHY THIS EXISTS
---------------
The medallion pipeline writes in order: Bronze, then Silver, then Gold. The
auto-refresh pass used to fetch every symbol first and only rebuild Silver/Gold
in a second loop afterwards. On this host the backend process never survived
long enough to reach that second loop — WSL tears the distro down every few
minutes (see `InitTerminateInstanceInternal` in the WSL journal, documented in
`check_wsl_keepalive.sh`) — so Bronze advanced every trading day while Silver
and Gold stayed frozen on the last clean pass. The visible symptom is that the
web UI shows data ~3 days older than what Bronze already holds.

Auto-refresh now rebuilds per symbol so it makes durable progress, but the
backlog left behind by the old behaviour still has to be cleared once. That is
what this script is for: it walks Bronze's symbol set, compares the Bronze and
Gold watermarks, and rebuilds only the symbols that are actually stale.

IDEMPOTENT
----------
Silver and Gold writes are full re-materialisations of the symbol, so running
this twice produces the same result. It is safe to interrupt and restart: the
work is per symbol, and a finished symbol is never rebuilt again because the
next run sees its watermarks aligned.

RELATIONSHIP TO AUTO-REFRESH
----------------------------
This is safe to run while the backend is up. Both paths write the same symbol
under the same partition prefix, and each write replaces the symbol's
partitions object by object; only wasted work can result, never corruption.
Stop the backend if you would rather not have the overlap.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import get_logger
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.session import session_date
from app.pipelines.orchestrator import build_gold_layer, transform_to_silver
from app.services.market_service import clear_symbol_cache

logger = get_logger(__name__)

BRONZE_PREFIX = "symbol="


def bronze_symbols() -> list[str]:
    """Every symbol that exists in the Bronze bucket.

    Derived from object keys rather than a hardcoded ticker list so the script
    covers whatever Bronze actually holds, including symbols added since the
    constants file was last touched.
    """
    bronze = BronzeLayer()
    objects = bronze.storage.list_objects("bronze", "")
    symbols: set[str] = set()
    for key in objects:
        # Keys look like "symbol=AAPL/year=2026/month=10/part-001.parquet".
        # The trailing slash in the prefix test keeps "symbol=M" from matching
        # "symbol=MA/" and friends.
        if not key.startswith(BRONZE_PREFIX):
            continue
        head = key.split("/", 1)[0]
        symbols.add(head.split("=", 1)[1])
    return sorted(symbols)


def _session_date(ts: pd.Timestamp | None) -> date | None:
    """Reduce a stored timestamp to the calendar day it belongs to.

    Delegates to the shared helper so the script and the auto-refresh service
    agree on what "the same trading day" means. See
    ``app.lakehouse.session.session_date`` for why raw timestamps cannot be
    compared directly between the Bronze and Gold layers.
    """
    return session_date(ts)


def stale_symbols(symbols: list[str], gold: GoldLayer, bronze: BronzeLayer) -> list[str]:
    """Return the symbols whose Gold watermark is behind (or missing vs) Bronze.

    The comparison is per trading day, not per timestamp - see
    :func:`_session_date` for why the raw timestamps of the two layers can
    differ by hours while describing the same session.
    """
    stale: list[str] = []
    for symbol in symbols:
        try:
            bronze_ts = bronze.latest_timestamp(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("watermark read failed for %s: %s", symbol, exc)
            continue
        if bronze_ts is None:
            continue
        try:
            gold_ts = gold.latest_timestamp(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("gold watermark read failed for %s: %s", symbol, exc)
            stale.append(symbol)
            continue
        bronze_day = _session_date(bronze_ts)
        gold_day = _session_date(gold_ts)
        if gold_day is None or gold_day < bronze_day:
            stale.append(symbol)
    return stale


def rebuild_one(symbol: str) -> dict:
    """Rebuild Silver then Gold for one symbol. Never raises."""
    started = time.monotonic()
    result = {"symbol": symbol, "silver": False, "gold": False, "error": None}
    try:
        transform_to_silver(symbol, interval="1d")
        result["silver"] = True
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"silver: {exc}"
        return result
    try:
        build_gold_layer(symbol)
        result["gold"] = True
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"gold: {exc}"
        return result
    # The backend memoises symbol frames with lru_cache and no TTL, so without
    # this the UI keeps serving the pre-rebuild snapshot until it restarts.
    try:
        clear_symbol_cache()
    except Exception:  # noqa: BLE001
        pass
    result["seconds"] = round(time.monotonic() - started, 1)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Explicit symbols to rebuild. Default: every stale symbol in Bronze.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which symbols are stale and exit without writing.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Symbols rebuilt in parallel (default 4). Each worker reads a whole "
        "symbol history from MinIO, so higher values mostly add memory pressure.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild every listed symbol, ignoring the watermark comparison. "
        "Use this after a CONTENT repair (a purge, a manual correction): the "
        "watermark only moves when the newest bar changes, so a symbol whose "
        "older rows were rewritten looks 'in sync' even though its Silver and "
        "Gold still hold the old rows.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Rebuild at most N symbols. Useful to chip away at a large backlog.",
    )
    args = parser.parse_args(argv)

    started_at = datetime.now(timezone.utc)

    print("Reading the Bronze symbol set ...")
    if args.symbols:
        candidates = [s.strip().upper() for s in args.symbols if s.strip()]
        print(f"  using {len(candidates)} symbol(s) from --symbols")
    else:
        candidates = bronze_symbols()
        print(f"  Bronze holds {len(candidates)} symbol(s)")

    if not candidates:
        print("No symbols found; nothing to do.")
        return 0

    if args.force:
        stale = list(candidates)
        print(f"  --force: rebuilding all {len(stale)} symbol(s)")
    else:
        print("Comparing Bronze and Gold watermarks ...")
        stale = stale_symbols(candidates, GoldLayer(), BronzeLayer())
        print(f"  {len(stale)}/{len(candidates)} symbol(s) need Silver/Gold rebuild")

    if args.limit is not None:
        stale = stale[: args.limit]
        print(f"  limited to {len(stale)} symbol(s) by --limit")

    if not stale:
        print("Everything is already in sync.")
        return 0

    if args.dry_run:
        print("Stale symbols (dry run, nothing written):")
        for symbol in stale:
            print(f"  {symbol}")
        return 0

    print(f"Rebuilding with {args.workers} worker(s) ...")
    rebuilt = 0
    failed: list[dict] = []
    progress_every = max(1, min(25, len(stale) // 10 or 1))

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(rebuild_one, symbol): symbol for symbol in stale}
        for done, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            if result["error"]:
                failed.append(result)
                logger.warning("rebuild failed for %s: %s", result["symbol"], result["error"])
            else:
                rebuilt += 1
            if done % progress_every == 0 or done == len(stale):
                elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                rate = done / elapsed if elapsed > 0 else 0.0
                remaining = len(stale) - done
                eta = remaining / rate if rate > 0 else 0.0
                print(
                    f"  {done}/{len(stale)} done | ok={rebuilt} failed={len(failed)} "
                    f"| {rate:.2f} sym/s | ETA {eta / 60:.1f} min"
                )

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    print()
    print(f"Rebuilt {rebuilt}/{len(stale)} symbol(s) in {elapsed / 60:.1f} min")
    if failed:
        print(f"{len(failed)} symbol(s) failed:")
        for result in failed[:20]:
            print(f"  {result['symbol']}: {result['error']}")
        if len(failed) > 20:
            print(f"  ... and {len(failed) - 20} more")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
