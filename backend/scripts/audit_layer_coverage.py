"""Find symbols whose Silver or Gold layer is missing partitions.

WHY THIS EXISTS
---------------
The concurrent partition writer used to log a failed write and continue. A
MinIO connection reset - routine while the refresh pass loads the same
instance - failed 110 of VCB's 202 Silver partitions. The write still
reported success, the quality report still said "passed", and the layer was
left holding 1,853 of its 4,080 rows with nothing anywhere saying so.

The failure is invisible from the read side: the reader gets a plausible,
correctly priced, SHORTER history and cannot tell it is truncated.

This script compares the partition months and row counts across the three
layers and reports every symbol where a downstream layer is missing
partitions that the upstream layer has.

Run from the backend directory:

    .venv/Scripts/python.exe scripts/audit_layer_coverage.py
    .venv/Scripts/python.exe scripts/audit_layer_coverage.py --repair
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.core.logging_config import get_logger, setup_logging  # noqa: E402

logger = get_logger(__name__)


def partition_months(storage, layer: str, symbol: str) -> set[str]:
    """The set of ``YYYY-MM`` months a symbol occupies in a layer."""
    months: set[str] = set()
    for key in storage.list_objects(layer, f"symbol={symbol}/"):
        if not key.endswith(".parquet"):
            continue
        if "year=" not in key or "month=" not in key:
            continue
        year = key.split("year=")[1].split("/")[0]
        month = key.split("month=")[1].split("/")[0]
        months.add(f"{year}-{month}")
    return months


def row_count(storage, layer: str, symbol: str) -> int:
    """The number of rows a symbol holds in a layer."""
    total = 0
    for key in storage.list_objects(layer, f"symbol={symbol}/"):
        if not key.endswith(".parquet"):
            continue
        frame = storage.read_parquet(layer, key)
        total += len(frame)
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Rebuild Silver and Gold for every symbol the audit flags.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Audit only these symbols.",
    )
    args = parser.parse_args(argv)

    setup_logging()

    from app.lakehouse.bronze import BronzeLayer
    from app.lakehouse.storage_factory import get_storage_backend
    from app.pipelines.orchestrator import build_gold_layer, transform_to_silver

    storage = get_storage_backend()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols if s.strip()]
    else:
        symbols = sorted(
            {
                name.split("/", 1)[0].split("=", 1)[1].upper()
                for name in (
                    obj.object_name or "" for obj in storage.client.list_objects(
                        storage._bucket("bronze"), prefix="symbol=", recursive=False
                    )
                )
                if name.startswith("symbol=")
            }
        )

    print(f"auditing {len(symbols)} symbol(s) across bronze/silver/gold\n")

    flagged: list[tuple[str, str, int, int]] = []
    for index, symbol in enumerate(symbols, start=1):
        bronze_months = partition_months(storage, "bronze", symbol)
        if not bronze_months:
            continue
        silver_months = partition_months(storage, "silver", symbol)
        gold_months = partition_months(storage, "gold", symbol)

        missing_silver = bronze_months - silver_months
        missing_gold = bronze_months - gold_months
        if not missing_silver and not missing_gold:
            continue

        silver_rows = row_count(storage, "silver", symbol)
        gold_rows = row_count(storage, "gold", symbol)
        flagged.append((symbol, "silver" if missing_silver else "gold", silver_rows, gold_rows))
        print(
            f"  {symbol:<12} bronze={len(bronze_months):>4}mo  "
            f"silver={len(silver_months):>4}mo ({silver_rows:>5} rows)  "
            f"gold={len(gold_months):>4}mo ({gold_rows:>5} rows)"
        )
        if missing_silver:
            print(f"       missing silver months: {sorted(missing_silver)[:8]}")
        if missing_gold:
            print(f"       missing gold months:   {sorted(missing_gold)[:8]}")

    print()
    if not flagged:
        print("PASS: every symbol's Silver and Gold layers cover its Bronze months.")
        return 0

    print(f"FAIL: {len(flagged)} symbol(s) have a truncated Silver or Gold layer.")
    if not args.repair:
        print("Re-run with --repair to rebuild them from Bronze.")
        return 1

    print()
    print("repairing...")
    for symbol, _, _, _ in flagged:
        try:
            transform_to_silver(symbol, interval="1d")
            build_gold_layer(symbol)
            print(f"  {symbol:<12} rebuilt")
        except Exception as exc:  # noqa: BLE001 - one symbol must not stop the rest
            logger.warning("repair failed for %s: %s", symbol, exc)
            print(f"  {symbol:<12} FAILED: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
