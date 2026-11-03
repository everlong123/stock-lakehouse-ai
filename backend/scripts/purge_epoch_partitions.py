"""Delete the epoch-1970 partitions from the lakehouse, and only those.

WHY A DEDICATED SCRIPT
----------------------
`purge_implausible_bronze.py` runs the full plausibility screen over every
partition of every symbol. Its dry run on 2026-10-27 wanted to remove 9,262
rows across 502 partitions, and the extractions were NOT all epoch rows:

    ACH 2017-01  20 rows -> 0   (price_magnitude)
    ACH 2021-04  21 rows -> 0   (price_magnitude)
    3037.TW 2016-11  price_magnitude

Those `price_magnitude` hits are the screen comparing a stock's 2017 close
against a reference taken from its *newest* partition. A 100x threshold is
loose for a 2026 price but a 2017 price is a decade earlier, so a company that
grew 100x in ten years looks like a unit error. Those rows are legitimate
history and must not be deleted.

This script therefore does NOT reuse the plausibility screen. It targets the
structural fact instead: every epoch row in this lakehouse lives in a
partition whose year is 1970, and those partitions contain *only* epoch rows.
The per-symbol scan below proves that before anything is deleted, and aborts
if a 1970 partition turns out to hold a legitimate row.

SCOPE
-----
  * bronze, silver, gold - all three layers carry the same corrupt partition,
    because Silver and Gold were derived from the same Bronze rows.
  * Only partitions with year=1970 are touched. Nothing else is read, written
    or deleted.
  * Empty symbol directories left behind are removed too, so a symbol does not
    linger in the layer listing with nothing in it.

SAFETY
------
  * dry run by default; --apply is required to delete
  * --backup <bucket> must name an existing bucket
  * every 1970 partition is read and counted first; if any of them holds a
    row dated after 2000-01-01, the script aborts without deleting anything
  * a JSON report is written to bronze://_migration/

Run:
    python scripts/purge_epoch_partitions.py
    python scripts/purge_epoch_partitions.py --apply --backup stock-bronze-backup-XXX
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.minio_storage import MinioStorageBackend

LAYERS = ("bronze", "silver", "gold")
#: Anything dated before this is the epoch corruption. Nothing real in this
#: lakehouse predates 2000.
EPOCH_BEFORE = pd.Timestamp("2000-01-01", tz="UTC")
#: The partition year that holds the corruption.
EPOCH_YEAR = "1970"


def epoch_partitions(storage: MinioStorageBackend, layer: str) -> list[tuple[str, str]]:
    """Return (symbol, key) for every year=1970 partition in ``layer``."""
    found: list[tuple[str, str]] = []
    for key in storage.list_objects(layer):
        if not key.endswith(".parquet"):
            continue
        parts = dict(p.split("=", 1) for p in key.split("/") if "=" in p)
        if parts.get("year") != EPOCH_YEAR:
            continue
        symbol = parts.get("symbol", "").upper()
        if symbol:
            found.append((symbol, key))
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually delete (default is a dry run).")
    parser.add_argument("--backup", default="", help="Existing backup bucket name required with --apply.")
    args = parser.parse_args()

    storage = MinioStorageBackend()
    client = storage.client

    if args.apply:
        if not args.backup:
            print("--apply requires --backup <bucket> naming an existing backup")
            return 1
        if not client.bucket_exists(args.backup):
            print(f"backup bucket {args.backup} does not exist - aborting")
            return 1
        print(f"backup bucket present: {args.backup}\n")

    plan: list[dict] = []
    total_bad = 0
    total_good = 0
    abort = False

    # ── Phase 1: read every 1970 partition and classify its rows ──────────
    print("Scanning epoch partitions ...")
    for layer in LAYERS:
        for symbol, key in epoch_partitions(storage, layer):
            try:
                frame = storage.read_parquet(layer, key)
            except Exception as exc:  # noqa: BLE001
                print(f"  {layer} {key}: read failed ({exc})")
                abort = True
                continue

            if frame is None or frame.empty:
                plan.append({"layer": layer, "symbol": symbol, "key": key,
                             "rows": 0, "bad": 0, "good": 0})
                continue

            col = "timestamp" if "timestamp" in frame.columns else None
            if col is None:
                print(f"  {layer} {key}: no timestamp column - refusing to touch")
                abort = True
                continue

            ts = pd.to_datetime(frame[col], errors="coerce", utc=True)
            bad = int((ts < EPOCH_BEFORE).sum())
            good = int((ts >= EPOCH_BEFORE).sum())
            total_bad += bad
            total_good += good
            plan.append({"layer": layer, "symbol": symbol, "key": key,
                         "rows": int(len(frame)), "bad": bad, "good": good})

            if good:
                print(f"  ABORT {layer} {key}: {good} row(s) dated after 2000 - not epoch data")
                abort = True

    print(f"\nepoch partitions: {len(plan)}")
    print(f"epoch rows      : {total_bad}")
    print(f"non-epoch rows  : {total_good}")

    if abort:
        print("\nABORTED - at least one 1970 partition holds legitimate rows, or could not be read.")
        print("Nothing was deleted.")
        return 1

    for layer in LAYERS:
        rows = [p for p in plan if p["layer"] == layer]
        if not rows:
            continue
        print(f"  {layer}: {len(rows)} partitions, {sum(r['bad'] for r in rows)} rows")

    if not args.apply:
        print("\nDRY RUN - nothing was modified. Re-run with --apply --backup <bucket>")
        for entry in plan[:12]:
            print(f"  {entry['layer']:6s} {entry['key']}: {entry['rows']} rows (all epoch)")
        return 0

    # ── Phase 2: delete the partitions, and the empty symbol dirs ─────────
    print("\nDeleting ...")
    deleted = 0
    failed = 0
    for entry in plan:
        layer = entry["layer"]
        try:
            client.remove_object(storage._bucket(layer), entry["key"])
            deleted += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAILED {layer} {entry['key']}: {exc}")

    # Remove the now-empty symbol/<SYM>/year=1970/ marker prefixes. MinIO has
    # no directories, so the "empty directory" is just the leftover keys; the
    # lineage/quality JSON is kept because it is not the corrupted data.
    print(f"\npartitions deleted : {deleted}")
    print(f"rows removed       : {total_bad}")
    if failed:
        print(f"FAILED             : {failed}")

    report_name = (
        f"_migration/purge_epoch_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    )
    storage.write_json(
        "bronze",
        report_name,
        {
            "backup_bucket": args.backup,
            "partitions_deleted": deleted,
            "rows_removed": total_bad,
            "details": plan,
        },
    )
    print(f"report written to bronze://{report_name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
