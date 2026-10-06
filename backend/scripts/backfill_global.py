"""Backfill Bronze for the GLOBAL_SYMBOLS universe (500+ tickers, 5 years).

Reuses the existing `ingest_all.py` pipeline under the hood so retries,
rate-limit handling and lineage tracking stay consistent.

Usage:
    python -m scripts.backfill_global [--workers 5] [--lookback 1825]

By default:
- Symbols  : app.core.constants.GLOBAL_SYMBOLS  (~500 tickers, US + EU + JP + HK + KR + TW + ...)
- Interval : 1d
- Lookback : 1825 days (5 years)
- Workers  : 5 concurrent requests (safe on Windows; bump if you have RAM headroom)

This is intentionally idempotent: re-running it will skip symbols whose Bronze
already has >= 0.9 * lookback days worth of daily bars.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import GLOBAL_SYMBOLS
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Bronze for global symbols (5y daily).")
    parser.add_argument("--workers", "-w", type=int, default=5,
                        help="Concurrent requests (default 5 — safe for Yahoo)")
    parser.add_argument("--lookback", "-l", type=int, default=1825,
                        help="Lookback days (default 1825 = 5 years)")
    parser.add_argument("--delay", "-d", type=float, default=0.5,
                        help="Seconds between requests (default 0.5)")
    parser.add_argument("--symbols", "-s", nargs="*", default=None,
                        help="Subset of symbols (default = all GLOBAL_SYMBOLS)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan only, do not fetch")
    args = parser.parse_args()

    symbols = args.symbols if args.symbols else list(GLOBAL_SYMBOLS)

    logger.info("=" * 70)
    logger.info("GLOBAL BACKFILL — Bronze layer")
    logger.info("=" * 70)
    logger.info("Symbols  : %d", len(symbols))
    logger.info("Interval : 1d")
    logger.info("Lookback : %d days (~%.1f years)", args.lookback, args.lookback / 365.0)
    logger.info("Workers  : %d concurrent", args.workers)
    logger.info("Delay    : %.2fs between requests", args.delay)
    logger.info("=" * 70)

    if args.dry_run:
        logger.info("[dry-run] Would ingest:")
        for s in symbols[:20]:
            logger.info("  - %s", s)
        if len(symbols) > 20:
            logger.info("  ... and %d more", len(symbols) - 20)
        return 0

    # Delegate to ingest_all.py via in-process call so logs/lineage stay unified.
    from scripts.ingest_all import IngestConfig, run_ingestion

    config = IngestConfig(
        symbols=symbols,
        intervals=["1d"],
        lookback_days={"1d": args.lookback},
        batch_size=args.workers,
        request_delay=args.delay,
        verbose=True,
    )

    stats = run_ingestion(config)

    logger.info("=" * 70)
    logger.info("BACKFILL SUMMARY")
    logger.info("=" * 70)
    logger.info("Duration     : %.1f seconds", stats.duration_seconds())
    logger.info("Successful   : %d", stats.successful)
    logger.info("Failed       : %d", stats.failed)
    logger.info("Skipped      : %d", stats.skipped)
    logger.info("Records      : %s", f"{stats.total_records:,}")
    logger.info("Duplicates   : %s", f"{stats.total_duplicates:,}")
    if stats.errors:
        logger.warning("First 10 errors:")
        for err in stats.errors[:10]:
            logger.warning("  - %s", err)
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())