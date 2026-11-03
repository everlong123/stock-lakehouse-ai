"""Purge implausible Bronze rows for a specific set of symbols.

WHY THIS EXISTS
---------------
`backfill_silver_gold.py` decides "is this symbol stale?" by comparing the
newest Bronze timestamp with the newest Gold timestamp. That comparison is
only meaningful if Bronze's newest row is a real bar.

Two symbols carried a junk placeholder row at the top of Bronze:

    AVB  2026-10-05 04:00:00Z  open=NaN high=NaN low=NaN close=NaN volume=0
    WBD  2026-10-05 04:00:00Z  open=0.0  high=30.99 low=30.94 close=30.95 volume=40

Both came from `yfinance_python`, a provider that emits a single degenerate
row for a symbol the primary HTTP provider will not serve. The row sits in the
newest month partition, so `BronzeLayer.latest_timestamp` returns it, and
Bronze then looks permanently newer than Gold. The symptom is a symbol that
the backfill rebuilds on every pass and never converges - for WBD the Gold
layer was already correct through 2026-10-02.

The rows are removed, not repaired: there is no correct value to restore.
A weekend placeholder bar carries no price information, so deleting it is the
only honest option. The full history of every other row is left byte-for-byte
alone.

After the purge the affected symbols are rebuilt so Silver and Gold are
re-materialised from the cleaned Bronze.

Run from the backend directory:

    .venv/Scripts/python.exe scripts/purge_symbol_bronze_junk.py --symbols AVB WBD
    .venv/Scripts/python.exe scripts/purge_symbol_bronze_junk.py --symbols AVB WBD --apply
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app.core.logging_config import get_logger
from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend
from app.lakehouse.plausibility import screen_batch

logger = get_logger(__name__)

LAYER = "bronze"


def purge_symbol(storage: MinioStorageBackend, symbol: str, apply: bool) -> tuple[int, int]:
    """Remove implausible rows for one symbol. Returns (rows_before, rows_removed)."""
    keys = [
        k
        for k in storage.list_objects(LAYER, symbol_prefix(symbol))
        if k.endswith(".parquet")
    ]
    if not keys:
        print(f"  {symbol}: no Bronze partitions")
        return 0, 0

    rows_before = 0
    removed_total = 0

    for key in keys:
        frame = storage.read_parquet(LAYER, key)
        if frame is None or frame.empty or "timestamp" not in frame.columns:
            continue
        rows_before += len(frame)

        kept, report = screen_batch(frame)
        if report.rejected_rows == 0:
            continue

        removed_total += report.rejected_rows
        print(
            f"  {symbol}: {key}: {len(frame)} -> {len(kept)} "
            f"(removed {report.rejected_rows}: {report.reasons})"
        )
        for sample in report.samples:
            print(f"      sample: {sample}")

        if apply:
            if kept.empty:
                storage.client.remove_object(storage._bucket(LAYER), key)
            else:
                storage.write_parquet(LAYER, key, kept)

    return rows_before, removed_total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", required=True, help="Symbols to purge.")
    parser.add_argument("--apply", action="store_true", help="Actually delete rows (default: dry run).")
    args = parser.parse_args()

    storage = MinioStorageBackend()
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"mode: {mode}")
    print(f"symbols: {', '.join(args.symbols)}\n")

    total_removed = 0
    for raw in args.symbols:
        symbol = raw.strip().upper()
        _, removed = purge_symbol(storage, symbol, args.apply)
        total_removed += removed

    print(f"\ntotal rows removed: {total_removed}")
    if args.apply:
        report_name = (
            f"_migration/purge_symbol_junk_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
        )
        storage.write_json(
            LAYER,
            report_name,
            {
                "symbols": [s.strip().upper() for s in args.symbols],
                "rows_removed": total_removed,
                "applied_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        print(f"report written to bronze://{report_name}")
    else:
        print("DRY RUN - nothing was modified. Re-run with --apply")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
