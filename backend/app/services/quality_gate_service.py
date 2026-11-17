"""Runs the data quality gate and keeps its result where the API can read it.

WHY A SERVICE AND NOT A SCRIPT
------------------------------
The gate produces a snapshot that has to be READ by the API long after the
pass that produced it finished. A script that prints to stdout cannot do
that: the output is gone by the time somebody opens the page, and there is
no record of what the gate said yesterday.

So the gate runs from the cron entrypoint, and this service:

* writes the snapshot to the lakehouse's quality layer, so the API can
  serve it without re-running the gate (which costs a network call per
  symbol);
* keeps the provider-rotation CURSOR between passes, so the full sweep
  completes over several passes instead of always checking the same
  symbols;
* keeps a short HISTORY of the snapshots, so the page can show whether the
  verdict is IMPROVING or DEGRADING - a single snapshot says "the data is
  broken now", but a history says "it has been broken since Tuesday".

WHERE THE SNAPSHOT LIVES
------------------------
In the lakehouse's ``quality`` layer, next to the data it describes. That
means the snapshot travels with the data: a backup of the lakehouse carries
the evidence of the lakehouse's own cleanliness, and the snapshot is
written by the same storage backend that wrote the data - MinIO in
production, the local filesystem in a demo - so there is no second source
of truth to keep in sync.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging_config import get_logger
from app.core.quality_gate import QualityGateReport, run_gate

logger = get_logger(__name__)

#: Where the latest snapshot is written inside the quality layer.
LATEST_KEY = "_gate/latest.json"

#: Where the rotation cursor lives between passes.
#:
#: It is stored NEXT to the snapshot rather than in the database, because it
#: is state about the LAKEHOUSE, not about the application. If the database
#: is down, the gate must still be able to run and to remember where it
#: was - otherwise every outage would reset the sweep to the first symbols
#: and the tail of the universe would never be checked.
ROTATION_KEY = "_gate/rotation.json"

#: How many snapshots the history keeps.
#:
#: 30 is enough to show a month of trend on the page, and small enough that
#: the history directory stays trivial to read.
HISTORY_LIMIT = 30


def _quality_storage():
    """The storage backend used for the gate's own artefacts.

    The lakehouse storage is used, and the ``quality`` layer maps to the
    Silver bucket in MinIO (see ``LAYER_BUCKETS``). That is deliberate: the
    gate's snapshot describes the Silver layer's quality, so it belongs
    beside it rather than in a bucket of its own that nobody would think
    to back up.
    """
    from app.lakehouse.storage_factory import get_storage_backend

    return get_storage_backend()


def _rotation_path() -> Path:
    """Where the rotation cursor lives on the local filesystem.

    The cursor is ALSO written to the storage layer, so it survives a
    container rebuild. The local copy is the fast path: reading a cursor
    must not cost a network round-trip, because it is read at the start of
    every pass.
    """
    from app.core.config import settings

    path = Path(settings.data_root_path) / "quality_gate_rotation.json"
    return path


def load_rotation() -> dict:
    """Read the provider-rotation cursor.

    The local file is the fast path. The storage copy is the fallback, for
    the case where the local filesystem was reset - a fresh container, a
    wiped volume - but the storage layer survived.
    """
    path = _rotation_path()
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(payload, dict):
                return payload
        except Exception:  # noqa: BLE001 - a corrupt cursor restarts the sweep
            logger.warning("Quality gate rotation file is unreadable; restarting the sweep")

    try:
        payload = _quality_storage().read_json("quality", ROTATION_KEY)
        if isinstance(payload, dict):
            return payload
    except Exception:  # noqa: BLE001 - no cursor yet
        pass
    return {"cursor": 0}


def save_rotation(rotation: dict) -> None:
    """Persist the provider-rotation cursor."""
    path = _rotation_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rotation), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - the cursor is an optimisation
        logger.warning("Quality gate rotation file could not be written: %s", exc)
    try:
        _quality_storage().write_json("quality", ROTATION_KEY, rotation)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Quality gate rotation could not be written to storage: %s", exc)


def read_latest() -> dict | None:
    """The most recent gate snapshot, or None when the gate has never run.

    A snapshot that cannot be read is reported as ``None`` - "the gate has
    not run", not "the gate passed". The API renders the two differently.
    """
    try:
        payload = _quality_storage().read_json("quality", LATEST_KEY)
    except Exception:  # noqa: BLE001
        return None
    return payload if isinstance(payload, dict) else None


def read_history(limit: int = HISTORY_LIMIT) -> list[dict]:
    """The recent gate snapshots, newest first.

    The history is read from the lakehouse's ``quality`` layer. Each
    snapshot is a separate object, so reading the newest few does not cost
    a download of the whole history.
    """
    storage = _quality_storage()
    try:
        keys = [
            key
            for key in storage.list_objects("quality", "_gate/history/")
            if key.endswith(".json")
        ]
    except Exception:  # noqa: BLE001
        return []

    history: list[dict] = []
    for key in sorted(keys, reverse=True)[:limit]:
        try:
            payload = storage.read_json("quality", key)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(payload, dict):
            history.append(payload)
    return history


def _history_key(report: QualityGateReport) -> str:
    """The history object's key for a snapshot.

    The timestamp is used as the key so the history sorts chronologically by
    key name, and the milliseconds are included so two passes in the same
    second do not overwrite each other.
    """
    stamp = report.checked_at.strftime("%Y%m%dT%H%M%S%f")
    return f"_gate/history/{stamp}.json"


def persist(report: QualityGateReport) -> None:
    """Write the snapshot to the lakehouse's quality layer."""
    storage = _quality_storage()
    payload = report.to_dict()
    try:
        storage.write_json("quality", LATEST_KEY, payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Quality gate snapshot could not be written: %s", exc)
        return
    try:
        storage.write_json("quality", _history_key(report), payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Quality gate history entry could not be written: %s", exc)


def run_and_persist(
    symbols: list[str] | None = None,
    provider_batch: int | None = None,
    provider_window: int | None = None,
    provider_name: str = "yahoo_http",
) -> dict:
    """Run the gate, persist the snapshot, and return it.

    This is the function the cron job calls. It never raises: a gate that
    dies must not take the cron timetable down with it, and the failure has
    to be recorded somewhere visible.
    """
    from app.core.quality_gate import PROVIDER_CHECK_BATCH, PROVIDER_CHECK_WINDOW

    rotation = load_rotation()
    try:
        report = run_gate(
            symbols=symbols,
            provider_batch=provider_batch or PROVIDER_CHECK_BATCH,
            provider_window=provider_window or PROVIDER_CHECK_WINDOW,
            provider_name=provider_name,
            rotation=rotation,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Data quality gate failed")
        payload = {
            "verdict": "failed",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": 0.0,
            "checks": {
                "gate": {
                    "status": "unavailable",
                    "checked": 0,
                    "failed": 0,
                    "warned": 0,
                    "reason": f"the gate could not run: {exc}",
                    "offenders": [],
                    "details": {},
                }
            },
            "provider_batch_size": 0,
            "provider_batch": [],
        }
        try:
            storage = _quality_storage()
            storage.write_json("quality", LATEST_KEY, payload)
        except Exception:  # noqa: BLE001
            pass
        return payload

    save_rotation(rotation)
    persist(report)
    return report.to_dict()


def summary() -> dict[str, Any]:
    """A compact view of the gate's state, for the API.

    The API does not want the whole snapshot - it wants the verdict, the
    per-check status, and enough history to say whether the verdict is
    improving or degrading.
    """
    latest = read_latest()
    if latest is None:
        return {
            "verdict": "unknown",
            "checked_at": None,
            "checks": {},
            "history": [],
            "note": "The quality gate has not run yet.",
        }

    history = read_history(limit=14)
    verdicts = [item.get("verdict") for item in history if isinstance(item, dict)]
    return {
        "verdict": latest.get("verdict"),
        "checked_at": latest.get("checked_at"),
        "elapsed_seconds": latest.get("elapsed_seconds"),
        "checks": latest.get("checks", {}),
        "history": [
            {
                "checked_at": item.get("checked_at"),
                "verdict": item.get("verdict"),
            }
            for item in history
            if isinstance(item, dict)
        ],
        "verdict_trend": _trend(verdicts),
    }


def _trend(verdicts: list[str]) -> str:
    """Whether the verdict is improving, degrading, or flat.

    The trend is computed from the history's oldest-to-newest order. The
    ranking is the same one the gate uses internally: a check that could
    not run is worse than a check that found a problem, because a problem
    is visible.
    """
    order = {"passed": 0, "warning": 1, "failed": 2, "unknown": 3}
    if len(verdicts) < 2:
        return "flat"
    ranked = [order.get(v, 2) for v in reversed(verdicts)]
    if ranked[-1] < ranked[0]:
        return "improving"
    if ranked[-1] > ranked[0]:
        return "degrading"
    return "flat"
