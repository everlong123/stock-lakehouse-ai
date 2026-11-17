"""Child-process entry points for the lakehouse rebuild jobs.

WHY A SEPARATE PROCESS
-----------------------
Rebuilding Silver and Gold for one symbol is the single most expensive piece
of work the auto-refresh pass does: it reads the symbol's whole history from
MinIO, canonicalises it, computes ~90 indicator columns and writes the
monthly partitions back.

It is also PURE PYTHON/PANDAS work, so in the API process it competes for the
GIL with the interactive request path. That is what turned a 2-second
walk-forward validation into a 96-second one and blew the agent's 75-second
deadline (see :mod:`app.core.heavy_worker` for the full measurement).

Running the rebuild in a child process gives it its own GIL, so:
  * the refresh still makes progress at the same wall-clock rate, and
  * the interactive path keeps a full core for itself.

The functions here are module-level and picklable so they can be sent to the
process pool.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def rebuild_silver_job(
    symbol: str,
    interval: str = "1d",
    changed_since: date | None = None,
) -> dict[str, Any]:
    """Rebuild Silver for one symbol and return a small summary dict.

    ``changed_since`` is the earliest session whose content may have
    changed. The Silver transform is row-local, so the earlier partitions
    would be rewritten with byte-identical content - 2.9 s of MinIO
    round-trips per symbol for nothing. None writes every partition.
    """
    from app.pipelines.orchestrator import transform_to_silver

    result = transform_to_silver(symbol, interval=interval, changed_since=changed_since)
    quality = result.get("quality") or {}
    return {
        "symbol": symbol,
        "records": quality.get("record_count"),
        "quality_status": quality.get("quality_status"),
        "paths": len((result.get("write") or {}).get("paths") or []),
    }


def rebuild_gold_job(symbol: str, changed_since: date | None = None) -> dict[str, Any]:
    """Rebuild Gold for one symbol and return a small summary dict.

    ``changed_since`` is the earliest session whose content may have
    changed. Every Gold feature is causal - it looks BACKWARD only - so a
    rebuild triggered by a new bar at the end of the history produces
    exactly the same rows for every earlier session. None writes every
    partition.
    """
    from app.pipelines.orchestrator import build_gold_layer

    write_info = build_gold_layer(symbol, changed_since=changed_since)
    return {
        "symbol": symbol,
        "records": write_info.get("records"),
        "paths": len(write_info.get("paths") or []),
    }
