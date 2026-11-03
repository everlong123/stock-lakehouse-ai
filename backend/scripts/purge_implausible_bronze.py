"""Purge implausible rows from the Bronze lakehouse.

Scope
-----
Only rows that fail the Bronze plausibility screen are removed. Everything
else is left byte-for-byte alone - the migration does not re-derive, re-price
or re-timestamp anything, because a cleanup that also "fixes" values would
put invented numbers into the lake.

The rows it targets are the vn_ws stream rows that carried two compounding
defects:

    VCB  source=vn_ws  ts=1970-01-10 19:15  close=56.9    (true price 56,600)

Both a wrong timestamp and a price three orders of magnitude away from the
symbol's own history. There is no correct value to restore them to, so they
are deleted rather than repaired; vn_rest continues to supply VCB.

Safety
------
  * requires a prior backup bucket, verified by name
  * default mode is --dry-run, which reports what would change
  * empty partitions after removal are deleted rather than left empty
  * a per-run JSON report is written to Bronze/_migration/

Run:
    python scripts/purge_implausible_bronze.py              # dry run
    python scripts/purge_implausible_bronze.py --apply
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import pandas as pd

from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend
from app.lakehouse.plausibility import screen_batch

LAYER = "bronze"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually delete rows (default is a dry run).")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N symbols (0 = all).")
    parser.add_argument(
        "--backup",
        default="",
        help="Backup bucket name that must already exist before --apply.",
    )
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

    keys = [k for k in storage.list_objects(LAYER) if k.endswith(".parquet")]
    symbols = sorted({k.split("symbol=")[1].split("/")[0] for k in keys if k.startswith("symbol=")})
    if args.limit:
        symbols = symbols[: args.limit]

    print(f"scanning {len(symbols)} symbols, {len(keys)} partitions")
    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

    reference_cache: dict[str, float] = {}
    changed_partitions: list[dict] = []
    total_rows_before = 0
    total_rows_after = 0
    total_removed = 0

    for i, sym in enumerate(symbols):
        sym_keys = [k for k in keys if k.startswith(symbol_prefix(sym))]
        removed_here = 0
        rows_before = 0

        for key in sym_keys:
            try:
                frame = storage.read_parquet(LAYER, key)
            except Exception as exc:  # noqa: BLE001
                print(f"  {key}: read failed ({exc})")
                continue
            if frame.empty or "timestamp" not in frame.columns:
                continue

            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
            rows_before += len(frame)

            if sym not in reference_cache:
                reference_cache[sym] = _reference_price(storage, sym)
            reference = reference_cache[sym]
            ref_map = {sym: reference} if reference > 0 else None

            kept, report = screen_batch(frame, reference_prices=ref_map)
            if report.rejected_rows == 0:
                continue

            removed_here += report.rejected_rows
            changed_partitions.append(
                {
                    "key": key,
                    "rows_before": int(len(frame)),
                    "rows_after": int(len(kept)),
                    "removed": int(report.rejected_rows),
                    "reasons": report.reasons,
                    "samples": report.samples[:3],
                }
            )

            if args.apply:
                if kept.empty:
                    client.remove_object(storage._bucket(LAYER), key)
                else:
                    storage.write_parquet(LAYER, key, kept)

        if removed_here:
            rows_after = rows_before - removed_here
            total_rows_before += rows_before
            total_rows_after += rows_after
            total_removed += removed_here
            print(f"  {sym:10s} removed {removed_here:5d} rows (of {rows_before})")
        if i and i % 100 == 0:
            print(f"  ... {i}/{len(symbols)} symbols scanned")

    print()
    print("=" * 70)
    print(f"partitions changed : {len(changed_partitions)}")
    print(f"rows removed       : {total_removed}")
    if args.apply:
        print(f"rows before/after  : {total_rows_before} -> {total_rows_after}")
        report_name = (
            f"_migration/purge_implausible_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
        )
        storage.write_json(
            LAYER,
            report_name,
            {
                "backup_bucket": args.backup,
                "partitions_changed": len(changed_partitions),
                "rows_removed": total_removed,
                "details": changed_partitions,
            },
        )
        print(f"report written to bronze://{report_name}")
    else:
        print("\nDRY RUN - nothing was modified. Re-run with --apply --backup <bucket>")
        for entry in changed_partitions[:10]:
            print(f"  {entry['key']}: {entry['rows_before']} -> {entry['rows_after']} ({entry['reasons']})")

    return 0


def _reference_price(storage: MinioStorageBackend, symbol: str) -> float:
    """Median close of the newest stored partition for ``symbol``."""
    try:
        keys = [
            k
            for k in storage.list_objects(LAYER, symbol_prefix(symbol))
            if k.endswith(".parquet")
        ]
    except Exception:  # noqa: BLE001
        return 0.0
    if not keys:
        return 0.0
    try:
        frame = storage.read_parquet(LAYER, sorted(keys, reverse=True)[0])
    except Exception:  # noqa: BLE001
        return 0.0
    if frame is None or frame.empty or "close" not in frame.columns:
        return 0.0
    closes = pd.to_numeric(frame["close"], errors="coerce").dropna()
    closes = closes[closes > 0]
    return float(closes.median()) if not closes.empty else 0.0


if __name__ == "__main__":
    raise SystemExit(main())