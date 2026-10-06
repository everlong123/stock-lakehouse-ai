"""Resume backfill for symbols not yet in Bronze (idempotent skip on existing)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import GLOBAL_SYMBOLS
from app.lakehouse.bronze import BronzeLayer
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def already_in_bronze() -> set[str]:
    """Symbols that already have at least one Bronze object."""
    bronze = BronzeLayer()
    keys = bronze.storage.list_objects("bronze", "symbol=")
    syms: set[str] = set()
    for k in keys:
        if k.startswith("symbol="):
            syms.add(k.split("/", 1)[0].split("=", 1)[1].upper())
    return syms


def main() -> int:
    existing = already_in_bronze()
    target = {s.upper() for s in GLOBAL_SYMBOLS}
    missing = sorted(target - existing)
    logger.info("Already in Bronze: %d / %d", len(existing), len(target))
    logger.info("Missing: %d", len(missing))
    if not missing:
        logger.info("All symbols already ingested. Nothing to do.")
        return 0

    # Delegate to ingest_all.py
    from scripts.ingest_all import IngestConfig, run_ingestion

    config = IngestConfig(
        symbols=missing,
        intervals=["1d"],
        lookback_days={"1d": 1825},
        batch_size=10,
        request_delay=0.3,
        verbose=True,
    )
    stats = run_ingestion(config)

    logger.info("Resume summary: success=%d failed=%d skipped=%d records=%s",
                stats.successful, stats.failed, stats.skipped,
                f"{stats.total_records:,}")
    if stats.errors:
        for e in stats.errors[:20]:
            logger.warning("  - %s", e)
    return 0 if stats.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())