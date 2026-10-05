"""Backfill Silver + Gold for every symbol that has Bronze data but no Gold.

Read-only with respect to Bronze: it only runs the Bronze -> Silver -> Gold
transform stages that were skipped for symbols ingested before the transform
service existed.

Usage:
    python -m scripts.backfill_gold [--workers 4] [--limit N] [--retry-failed]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.core.logging_config import get_logger
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.pipelines.orchestrator import (
    build_gold_layer,
    build_quality_report,
    transform_to_silver,
)

logger = get_logger(__name__)


def _symbols_in_layer(layer: str) -> set[str]:
    """Symbols that have at least one object under `layer`."""
    try:
        keys = BronzeLayer().storage.list_objects(layer, "symbol=")
    except Exception:
        return set()
    symbols = set()
    for key in keys:
        if not key.startswith("symbol="):
            continue
        sym = key.split("/", 1)[0].split("=", 1)[1].upper()
        if sym:
            symbols.add(sym)
    return symbols


def _symbols_with_bronze() -> set[str]:
    """Symbols that have at least one Bronze object."""
    return _symbols_in_layer("bronze")


def _symbols_with_gold() -> set[str]:
    """Symbols that already have Gold data (i.e. nothing to backfill)."""
    return _symbols_in_layer("gold")


def process(symbol: str, retries: int = 2) -> tuple[str, bool, str]:
    """Run Silver -> quality gate -> Gold for one symbol. Idempotent.

    Retries transient failures (connection resets, timeouts) that show up when
    many symbols are transformed in one run.
    """
    last = ""
    for attempt in range(retries + 1):
        try:
            transform_to_silver(symbol, interval="1d")
            quality = build_quality_report(symbol)
            if quality.get("quality_status") == "failed":
                return symbol, False, f"quality failed: {quality}"
            meta = build_gold_layer(symbol)
            return symbol, True, f"{meta.get('records', 0)} records"
        except Exception as exc:  # noqa: BLE001 - report per-symbol, keep going
            last = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    return symbol, False, last


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="1 = sequential (safest). >1 risks exhausting RAM on hosts "
        "without a pagefile.",
    )
    parser.add_argument("--limit", type=int, default=0, help="0 = all")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Extra attempts per symbol before marking it failed.",
    )
    args = parser.parse_args()

    bronze = _symbols_with_bronze()
    gold = _symbols_with_gold()
    # Only Gold is authoritative: a symbol can have a partial/failed Silver write
    # from a previous crashed run, so skipping on "has Silver" would strand it.
    todo = sorted(bronze - gold)
    if args.limit:
        todo = todo[: args.limit]

    logger.info(
        "Backfill target: bronze=%d gold=%d todo=%d workers=%d",
        len(bronze),
        len(gold),
        len(todo),
        args.workers,
    )
    if not todo:
        print("Nothing to backfill — every Bronze symbol already has Gold.")
        return 0

    ok, failed = [], []
    started = time.time()
    # Checkpoint every N symbols so a crash or interruption can be resumed with
    # --retry-failed without redoing work (transforms are idempotent but slow).
    checkpoint = Path("logs/backfill_checkpoint.json")
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process, sym, args.retries): sym for sym in todo
        }
        for i, fut in enumerate(as_completed(futures), 1):
            symbol, success, detail = fut.result()
            (ok if success else failed).append(symbol)
            if not success:
                logger.warning("FAILED %s: %s", symbol, detail)
            if i % 10 == 0 or i == len(todo):
                checkpoint.write_text(
                    json.dumps({"done": sorted(ok), "failed": sorted(failed)}),
                    encoding="utf-8",
                )
                rate = i / max(time.time() - started, 1e-6)
                print(
                    f"  {i}/{len(todo)} ok={len(ok)} failed={len(failed)} "
                    f"({rate:.1f}/s)",
                    flush=True,
                )

    print(f"\nDone. succeeded={len(ok)} failed={len(failed)}")
    if failed:
        print("Failed symbols:")
        for sym in failed:
            print(f"  - {sym}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
