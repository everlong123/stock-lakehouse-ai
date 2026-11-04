"""Concurrent partition writing for the medallion layers.

WHY THIS EXISTS
---------------
Bronze, Silver and Gold all split a symbol's history into one parquet file per
year/month. A 10-year daily ticker therefore has ~121 partitions, and writing
them one after another cost ~2.9s of serial MinIO round-trips for Silver and
~1.5s for Gold.

The auto-refresh pass rebuilds Silver+Gold for hundreds of symbols, so that
serial time dominated the refresh: the measured cost was ~15s per symbol, and
with 4 rebuild workers running alongside the HTTP handlers it starved the API
process of the GIL - a 1-second backtest took 100 seconds and blew past the
frontend's 90s timeout.

The writes are independent (each key is written exactly once, and a partition
is overwritten rather than appended to), so a thread pool is safe and turns
the serial round-trips into a handful of parallel ones.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Mapping

import pandas as pd

from app.core.exceptions import StorageError

# How many partitions to write in parallel. MinIO is a single node on local
# disk, so this is high enough to hide the round-trip latency without
# saturating the server.
#
# WHY 5 AND NOT 8: with 3 rebuild workers each writing 8 partitions at once
# (24 concurrent writes) MinIO started resetting connections - measured 22
# resets during a 30-symbol browse on 2026-11-03, and each reset stalled the
# read that hit it for up to 30s (the connect timeout).
#
# 5 x 3 workers = 15 concurrent writes, which the server handles without
# resetting, and a single symbol's write is still ~2x faster than serial.
WRITE_CONCURRENCY = int(os.getenv("MINIO_WRITE_CONCURRENCY", "5"))


def write_partitions_concurrently(
    storage,
    layer: str,
    partitions: Mapping[str, pd.DataFrame],
    max_workers: int = WRITE_CONCURRENCY,
) -> list[str]:
    """Write every partition concurrently and return the storage paths.

    WHY A FAILED PARTITION IS NOW FATAL
    ----------------------------------
    This function used to log a warning and continue when a partition could
    not be written, on the theory that "one bad object cannot leave a symbol
    half-written". But the opposite was true, and it was silent:

        A MinIO connection reset (which happens routinely while the
        auto-refresh pass is loading the same instance) failed 110 of VCB's
        202 Silver partitions. The write reported success, the quality
        report said "record_count: 4080, error_count: 0, quality_status:
        passed", and the Silver layer was left holding 92 partitions and
        1,853 of its 4,080 rows. Nothing anywhere said "you are missing
        2,227 rows".

    A partially written symbol is WORSE than an unwritten one, because the
    reader cannot tell the difference: it gets a plausible, correctly
    priced, shorter history with no indication that the rest is missing.
    The chart simply shows less, and the user has no way to know the
    history is truncated.

    So a failed partition now aborts the write with an error that names
    the partitions that did not land. The caller can retry; the symbol
    keeps its previous complete state rather than becoming a partial one.
    """
    if not partitions:
        return []

    paths: list[str] = []
    items = list(partitions.items())
    workers = max(1, min(max_workers, len(items)))
    failures: list[tuple[str, Exception]] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(storage.write_parquet, layer, relative_path, group): relative_path
            for relative_path, group in items
        }
        for future in futures:
            relative_path = futures[future]
            try:
                paths.append(future.result())
            except Exception as exc:  # noqa: BLE001 - collected and raised below
                failures.append((relative_path, exc))

    if failures:
        detail = "; ".join(f"{path}: {exc}" for path, exc in failures[:5])
        more = f" (+{len(failures) - 5} more)" if len(failures) > 5 else ""
        raise StorageError(
            f"Failed to write {len(failures)} of {len(items)} {layer} partitions: "
            f"{detail}{more}. The layer was NOT updated for the partitions that "
            f"failed - re-run the transform to retry."
        )

    return paths
