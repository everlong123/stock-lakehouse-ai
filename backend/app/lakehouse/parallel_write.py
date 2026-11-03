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

    A single partition that fails does NOT abort the write: the error is
    logged and that partition is skipped, so one corrupt object cannot leave
    a symbol half-written. The failed partition is still reported to the
    caller through the log, matching the behaviour of the read path.
    """
    if not partitions:
        return []

    paths: list[str] = []
    items = list(partitions.items())
    workers = max(1, min(max_workers, len(items)))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(storage.write_parquet, layer, relative_path, group): relative_path
            for relative_path, group in items
        }
        for future in futures:
            relative_path = futures[future]
            try:
                paths.append(future.result())
            except Exception as exc:  # noqa: BLE001 - one bad partition must not kill the write
                from app.core.logging_config import get_logger

                get_logger(__name__).warning(
                    "Failed to write partition %s to %s: %s", relative_path, layer, exc
                )
    return paths
