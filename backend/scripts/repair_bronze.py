"""Repair already-ingested Bronze rows that fail the Silver OHLC invariant.

Run from the backend directory:

    .venv/Scripts/python.exe scripts/repair_bronze.py --dry-run
    .venv/Scripts/python.exe scripts/repair_bronze.py

WHY
---
On 2026-10-22 the Yahoo provider was found returning bars whose high was below
its own open/close (and vice versa). Those bars reached Bronze unmodified, and
the Silver layer then rejected every one of them into `_errors/`, so the
symbols silently lost those rows instead of gaining them. `_normalize_ohlc` in
`app/data_sources/yahoo_http_provider.py` now fixes this at the source; this
script repairs the rows that are already in the lakehouse.

WHAT IT CHANGES
---------------
For a partition whose rows violate the invariant, the script rewrites the
whole partition with OHLC clamped so that

    low <= min(open, close) <= max(open, close) <= high

using the same rule as the provider. Rows that are unrepairable (non-positive
prices, or high below low by more than the bar's own width) are dropped, not
clamped.

Bronze is append-only by design, so this rewrites objects in place rather than
appending corrected copies. `--dry-run` reports exactly what would change and
writes nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app.core.logging_config import get_logger
from app.data_sources.yahoo_http_provider import YahooHttpProvider
from app.lakehouse.minio_storage import MinioStorageBackend

logger = get_logger(__name__)

LAYER = "bronze"


def violated(frame: pd.DataFrame) -> pd.Series:
    """Boolean mask of rows breaking the OHLC ordering invariant."""
    if frame.empty:
        return pd.Series(dtype=bool, index=frame.index)
    return (
        (frame["high"] < frame[["open", "close"]].max(axis=1))
        | (frame["low"] > frame[["open", "close"]].min(axis=1))
        | (frame["high"] < frame["low"])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument("--layer", default=LAYER, help="layer to repair (default: bronze)")
    args = parser.parse_args()

    storage = MinioStorageBackend()
    keys = [k for k in storage.list_objects(args.layer) if k.endswith(".parquet") and "_errors" not in k]
    logger.info("scanning %d objects in %s", len(keys), args.layer)

    bad_partitions: list[tuple[str, pd.DataFrame]] = []
    total_bad_rows = 0
    unreadable = 0

    for index, key in enumerate(keys, start=1):
        try:
            frame = storage.read_parquet(args.layer, key)
        except Exception as exc:  # noqa: BLE001 - report, keep scanning
            unreadable += 1
            logger.warning("unreadable %s: %s", key, exc)
            continue

        if not {"open", "high", "low", "close"}.issubset(frame.columns):
            continue

        mask = violated(frame)
        if mask.any():
            bad_partitions.append((key, frame.loc[mask].copy()))
            total_bad_rows += int(mask.sum())

        if index % 200 == 0:
            logger.info("  scanned %d/%d, %d bad rows so far", index, len(keys), total_bad_rows)

    logger.info("=" * 60)
    logger.info("partitions with violations : %d", len(bad_partitions))
    logger.info("violating rows             : %d", total_bad_rows)
    logger.info("unreadable objects         : %d", unreadable)

    if not bad_partitions:
        logger.info("nothing to repair")
        return 0

    logger.info("sample of violating rows:")
    for key, frame in bad_partitions[:3]:
        logger.info("  %s", key)
        logger.info(
            "    %s",
            frame[["symbol", "timestamp", "open", "high", "low", "close"]]
            .head(3)
            .to_string(index=False)
            .replace("\n", "\n    "),
        )

    if args.dry_run:
        logger.info("dry run: nothing written")
        return 1

    repaired_rows = 0
    dropped_rows = 0
    for key, _ in bad_partitions:
        frame = storage.read_parquet(args.layer, key)
        before = len(frame)
        fixed = YahooHttpProvider._normalize_ohlc(frame)
        dropped_rows += before - len(fixed)
        if fixed.empty:
            logger.warning("%s: every row unrepairable, deleting object", key)
            storage.client.remove_object(storage._bucket(args.layer), key)
            continue
        storage.write_parquet(args.layer, key, fixed)
        repaired_rows += len(fixed)

    logger.info("=" * 60)
    logger.info("rewrote %d partition(s)", len(bad_partitions))
    logger.info("rows now valid              : %d", repaired_rows)
    logger.info("rows dropped as unrepairable: %d", dropped_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())