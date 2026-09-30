"""Build Gold layer features for every symbol that already has Silver data.

Useful as a one-shot recovery when an earlier ingestion run wrote
Bronze + Silver but failed at the Gold step (e.g. contaminated Silver
parquet files that broke ``add_composite_signals``).

The Gold feature builder is now idempotent (see
``app.features.feature_engineering.build_gold_features``) so this
script can be safely re-run.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.logging_config import get_logger
from app.lakehouse import GoldLayer, SilverLayer
from app.lakehouse.storage_factory import get_storage_backend

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Gold features from existing Silver data.",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbols to rebuild. Defaults to all Silver symbols.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of symbols (useful for smoke tests).",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def discover_silver_symbols() -> list[str]:
    storage = get_storage_backend()
    keys = storage.list_objects("silver", prefix="")
    symbols: set[str] = set()
    for key in keys:
        if key.startswith("symbol="):
            symbol = key.split("/")[0].split("=", 1)[1]
            if symbol and not symbol.startswith("_"):
                symbols.add(symbol.upper())
    return sorted(symbols)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.quiet:
        import logging

        logging.getLogger().setLevel(logging.WARNING)

    silver = SilverLayer()
    gold = GoldLayer()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = discover_silver_symbols()

    if args.limit:
        symbols = symbols[: args.limit]

    logger.info("=" * 70)
    logger.info("GOLD RECOVERY")
    logger.info("Symbols: %s", len(symbols))
    logger.info("=" * 70)

    success = failed = 0
    total_rows = 0
    started = time.time()
    for index, symbol in enumerate(symbols, start=1):
        silver_frame = silver.read(symbol)
        if silver_frame.empty:
            logger.info("[%d/%d] %s - empty Silver, skipping", index, len(symbols), symbol)
            continue
        try:
            gold_frame = gold.transform(silver_frame)
            if gold_frame is None or gold_frame.empty:
                logger.warning("[%d/%d] %s - transform produced empty frame", index, len(symbols), symbol)
                failed += 1
                continue
            result = gold.write(gold_frame)
            rows = result.get("records", len(gold_frame))
            total_rows += rows
            success += 1
            logger.info(
                "[%d/%d] [OK] %s silver=%d gold=%d (%d partitions)",
                index,
                len(symbols),
                symbol,
                len(silver_frame),
                rows,
                len(result.get("paths", [])),
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.error("[%d/%d] [FAIL] %s - %s", index, len(symbols), symbol, exc)

    elapsed = time.time() - started
    logger.info("=" * 70)
    logger.info("GOLD RECOVERY COMPLETE")
    logger.info("Success: %d | Failed: %d | Total symbols: %d", success, failed, len(symbols))
    logger.info("Gold rows written: %d", total_rows)
    logger.info("Elapsed: %.1fs", elapsed)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()