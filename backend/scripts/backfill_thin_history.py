"""Backfill full history for symbols whose Bronze history is thin.

WHY THIS EXISTS
---------------
The lakehouse was seeded by a rolling refresh, which only ever fetched a
recent window. Symbols that were added to the universe later - or whose
first ingest happened recently - therefore hold only a couple of years of
daily bars while the provider has a decade.

Measured on 2026-11-04 (gold layer):

    VCB   532 rows  2024-10-07 -> 2026-11-04   (provider has 2623 from 2016)
    FPT   534 rows  2024-10-07 -> 2026-11-04
    HPG   534 rows  2024-10-07 -> 2026-11-04
    MWG   532 rows  2024-10-07 -> 2026-11-04
    SOFI    6 rows  2026-10-09 -> 2026-10-16    (provider has 1466 from 2016)

A chart of those symbols looked complete - it had bars, they were correctly
priced - but it silently answered a different question than the reader
asked. "Show me VCB" should mean the whole history, not "the two years
somebody happened to have loaded".

The provider is asked for the full range it serves; the rows that come back
go through the same plausibility screen as any other ingest, so nothing
bypasses validation.

Run from the backend directory:

    .venv/Scripts/python.exe scripts/backfill_thin_history.py
    .venv/Scripts/python.exe scripts/backfill_thin_history.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.core.constants import ALL_SYMBOLS, VN_SYMBOLS  # noqa: E402
from app.core.logging_config import get_logger, setup_logging  # noqa: E402

logger = get_logger(__name__)

#: A symbol with fewer than this many daily bars is considered thin.
#:
#: A decade of trading days is ~2500. Anything under 2000 has a visible
#: missing tail on the chart.
THIN_ROW_THRESHOLD = 2000

#: How far back to ask the provider for. Yahoo serves ~10 years of daily
#: bars; asking for more is free (it clamps) and asking for less would
#: truncate the history that exists.
HISTORY_START = datetime(2010, 1, 1, tzinfo=timezone.utc)


def bronze_symbols() -> list[str]:
    """Every symbol that has rows in Bronze."""
    from app.lakehouse.storage_factory import get_storage_backend

    storage = get_storage_backend()
    symbols: set[str] = set()
    for obj in storage.client.list_objects(
        storage._bucket("bronze"), prefix="symbol=", recursive=False
    ):
        name = obj.object_name or ""
        if name.startswith("symbol="):
            symbol = name.split("/", 1)[0].split("=", 1)[1].upper()
            if symbol:
                symbols.add(symbol)
    return sorted(symbols)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which symbols are thin and exit without writing.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Explicit symbols to check. Default: every symbol in Bronze.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=THIN_ROW_THRESHOLD,
        help=f"Row count below which a symbol counts as thin (default {THIN_ROW_THRESHOLD}).",
    )
    parser.add_argument(
        "--include-vn",
        action="store_true",
        help="Also check the Vietnamese symbols. Off by default because most "
             "of them are served by SSI iBoard, which the Yahoo provider "
             "cannot fetch for every ticker.",
    )
    args = parser.parse_args(argv)

    setup_logging()

    from app.data_sources.factory import get_data_provider
    from app.lakehouse.bronze import BronzeLayer
    from app.pipelines.orchestrator import build_gold_layer, transform_to_silver

    if args.symbols:
        candidates = [s.strip().upper() for s in args.symbols if s.strip()]
    else:
        candidates = bronze_symbols()
        if not args.include_vn:
            candidates = [s for s in candidates if s not in set(VN_SYMBOLS)]

    provider = get_data_provider("yahoo_http")
    bronze = BronzeLayer()

    thin: list[tuple[str, int, str]] = []
    for symbol in candidates:
        frame = bronze.read(symbol)
        if frame.empty:
            thin.append((symbol, 0, "empty"))
            continue
        count = len(frame)
        if count >= args.threshold:
            continue
        timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        first = timestamps.min()
        thin.append((symbol, count, str(first.date()) if pd.notna(first) else "?"))

    if not thin:
        print("Every symbol has a full history. Nothing to backfill.")
        return 0

    print(f"{'symbol':<12} {'rows':>8}  first      action")
    print("-" * 52)
    for symbol, count, first in thin:
        print(f"{symbol:<12} {count:>8}  {first:<10} backfill")

    if args.dry_run:
        print()
        print("DRY RUN - nothing was written. Re-run without --dry-run to backfill.")
        return 0

    print()
    failed: list[str] = []
    for symbol, _, _ in thin:
        try:
            frame = provider.get_historical_data(
                symbol, start=HISTORY_START, end=datetime.now(timezone.utc), interval="1d"
            )
            if frame is None or frame.empty:
                print(f"  {symbol:<12} no data from the provider - skipped")
                continue
            result = bronze.append(frame, lineage={"source": "history_backfill", "symbol": symbol})
            rejected = result.get("plausibility_rejected", 0)
            print(
                f"  {symbol:<12} fetched={len(frame):<6} written={result['records_written']:<6} "
                f"new={result['new_records']:<6} rejected={rejected}"
            )
            transform_to_silver(symbol, interval="1d")
            build_gold_layer(symbol)
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the rest
            logger.warning("backfill failed for %s: %s", symbol, exc)
            failed.append(symbol)

    print()
    print(f"Backfilled {len(thin) - len(failed)}/{len(thin)} symbol(s).")
    if failed:
        print(f"failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
