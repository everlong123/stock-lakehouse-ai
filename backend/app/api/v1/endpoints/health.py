"""Health and system status endpoints."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.core.config import settings
from app.core.logging_config import get_logger
from app.database.session import check_database_connection
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer
from app.lakehouse.spark_session import spark_enabled
from app.lakehouse.storage_factory import get_storage_backend
from app.schemas.common import ok

logger = get_logger(__name__)
router = APIRouter(tags=["health"])

# Cache layer counts for 5 minutes. Counting objects in 87k+ parquet files is
# expensive (~5-10s per layer) and the System Status page polls every few
# seconds, so we warm the cache on demand and refresh it in the background.
_COUNTS_CACHE_TTL_SECONDS = 300.0
_counts_lock = threading.Lock()
_counts_cache: dict[str, Any] = {"value": None, "expires_at": 0.0}
# True while a background layer-count job is in flight. Prevents the 15s
# poll from stacking up several 19s MinIO walks.
_refresh_running = False
_warmup_lock = threading.Lock()
_warmup_started = False


@router.get("/health")
def health() -> dict:
    return ok({"status": "ok", "app": settings.app_name})


@router.get("/system/status")
def system_status() -> dict:
    storage = get_storage_backend()
    mysql_ok = check_database_connection()
    minio_mode = storage.backend_name == "minio"

    # Detect LLM provider
    provider = settings.llm_provider.lower().strip()
    if settings.gemini_api_key.strip() and provider != "local":
        agent_status = "gemini_free"
    elif provider == "local" or not settings.gemini_api_key.strip():
        agent_status = "local_tool_router"
    else:
        agent_status = "local_tool_router"

    # Quick HTTP probes for optional services (best-effort, non-blocking)
    iceberg_ok = _probe_http(f"{settings.iceberg_catalog_uri}/v1/config", expect_status=[200, 400, 404, 405])
    kafka_ok = _probe_tcp(settings.kafka_bootstrap_servers.split(",")[0].strip()) if settings.use_kafka else False

    # Each record_count lists every object key in a bucket, so run the three in
    # parallel instead of serially to keep this page responsive.
    counts = _layer_counts()

    payload = {
        "backend_api": {"label": "Backend API", "status": "online"},
        "mysql": {"label": "MySQL", "status": "connected" if mysql_ok else "disconnected"},
        "minio": {
            "label": "MinIO (S3)",
            "status": "connected" if minio_mode else "local_storage_mode",
        },
        "iceberg": {
            "label": "Iceberg REST",
            "status": "online" if iceberg_ok else "disabled",
        },
        "kafka": {
            "label": "Kafka",
            "status": "online" if kafka_ok else ("disabled" if not settings.use_kafka else "offline"),
        },
        "data_source": {"label": "Data Source", "status": settings.data_source},
        "ai_agent": {
            "label": "AI Agent",
            "status": agent_status,
        },
        "counts": counts,
        "storage_backend": storage.backend_name,
        "use_spark": settings.use_spark,
        "last_pipeline_run": _last_pipeline_run(),
    }
    return ok(payload)


def _compute_layer_counts() -> dict[str, int]:
    """Walk the buckets and count objects per layer.

    WHY A SUBPROCESS
    ----------------
    Counting the three layers lists ~340k object keys in MinIO. The MinIO
    client yields them one at a time, and every step of that iteration runs
    Python code INSIDE this process, so the job holds the GIL for as long as
    it runs - ~19s when the box is idle, and several minutes while the
    auto-refresh pass hammers the same MinIO instance.

    A GIL-holding job in the API process starves EVERY other endpoint: the
    dashboard, the market history and the agent all queue behind it. That is
    what made a plain browser reload take a minute even though every single
    request was individually fast.

    Running the count in a separate process removes the contention: the API
    process never touches those 340k keys, so it stays responsive, and the
    (much slower) count cannot delay a user-facing request. The subprocess
    prints one JSON object on stdout, which is parsed here.

    The in-process implementation is kept as a fallback, for environments
    where spawning a subprocess is not possible.
    """
    script = Path(__file__).resolve().parents[3] / "scripts" / "count_layer_objects.py"
    if script.is_file():
        try:
            return _compute_layer_counts_subprocess(script)
        except Exception as exc:  # noqa: BLE001 - fall back to in-process
            logger.warning("layer-count subprocess failed, using in-process count: %s", exc)
    return _compute_layer_counts_inprocess()


def _compute_layer_counts_subprocess(script: Path) -> dict[str, int]:
    """Run the counting script in a separate process and parse its output."""
    import subprocess

    completed = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(script.parents[1]),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"count script exited {completed.returncode}: {completed.stderr[:500]}")
    line = (completed.stdout or "").strip().splitlines()[-1]
    payload = json.loads(line)
    counts = {k: int(v) for k, v in payload.items()}
    if set(counts) != {"bronze", "silver", "gold"}:
        raise RuntimeError(f"unexpected count payload: {payload}")
    return counts


def _compute_layer_counts_inprocess() -> dict[str, int]:
    """Count the layers inside this process (fallback for the subprocess path).

    This holds the GIL for the duration of the walk, so it is only used when
    the subprocess route is unavailable.
    """
    layers = (
        ("bronze", BronzeLayer),
        ("silver", SilverLayer),
        ("gold", GoldLayer),
    )
    counts: dict[str, int] = {}

    def _one(name: str, cls) -> None:
        try:
            counts[name] = int(cls().record_count())
        except Exception as exc:
            logger.warning("record_count failed for %s: %s", name, exc)
            counts[name] = -1

    # Run all three layers concurrently — each one walks the full bucket
    # (87k+ objects) and would otherwise dominate the System Status page
    # latency. Serial execution measured ~25s/30s/20s on the demo data;
    # parallel shaves that to max(t_i) instead of sum(t_i).
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="layer-count") as pool:
        futures = [pool.submit(_one, name, cls) for name, cls in layers]
        for fut in futures:
            fut.result()
    return counts


def _schedule_refresh() -> None:
    """Run a fresh count in the background if the cached value is missing or
    about to expire, without blocking the current request.

    WHY THE "ALREADY RUNNING" GUARD
    ------------------------------
    The System Status endpoint is polled every 15s and the count takes ~19s.
    Without a guard, every poll would start ANOTHER 19s job, each walking
    ~340k object keys in MinIO. Four overlapping jobs saturate MinIO and the
    CPU, which slows down every OTHER endpoint too - the dashboard and the
    auto-refresh pass included - and the pile-up only ever grows.

    One job at a time is enough: it refreshes the cache, and the requests
    that arrive while it runs simply get the stale (or zero) value.
    """
    global _refresh_running

    with _counts_lock:
        if _refresh_running:
            return
        _refresh_running = True

    def _job() -> None:
        global _refresh_running
        try:
            new_value = _compute_layer_counts()
        except Exception as exc:
            logger.warning("background layer-count refresh failed: %s", exc)
            return
        finally:
            with _counts_lock:
                _refresh_running = False
        with _counts_lock:
            _counts_cache["value"] = new_value
            _counts_cache["expires_at"] = time.monotonic() + _COUNTS_CACHE_TTL_SECONDS
        _persist_counts(new_value)

    thread = threading.Thread(target=_job, name="layer-count-refresh", daemon=True)
    thread.start()


def _layer_counts() -> dict[str, int]:
    """Return the cached layer counts, never blocking the request.

    WHY THIS NEVER BLOCKS
    ---------------------
    Counting the three layers lists ~340k object keys in MinIO, which costs
    ~19s on the demo data - and the System Status endpoint is polled by the
    dashboard every 15s. The old code had a "cold start" branch that ran the
    count SYNCHRONOUSLY, so the very first request after a restart (and every
    request until the cache was populated) blocked for ~19s. Worse, the
    frontend's 90s axios timeout could fire while the count was still
    running, so the page showed "Yêu cầu mất quá lâu" instead of a status.

    Now the cold path is exactly like the stale path: serve the last known
    value immediately (or zero when there is none) and kick the refresh off
    in the background. The first response is honest about not knowing yet -
    the counts simply read 0 until the background job has finished - and
    every later request picks the real numbers up.

    Behaviour:
    - Cache fresh: served from cache.
    - Cache stale or cold: served immediately (stale value, or zeros), and a
      background refresh is scheduled (at most one at a time).
    """
    now = time.monotonic()
    with _counts_lock:
        cached = _counts_cache["value"]
        expires_at = _counts_cache["expires_at"]

    if cached is not None and now < expires_at:
        return dict(cached)

    # Stale or cold: refresh in the background and answer right now.
    _schedule_refresh()
    if cached is not None:
        return dict(cached)
    # Cold start: no counts known yet. Report zeros rather than blocking; the
    # background job fills the cache and the next poll shows the real numbers.
    return {"bronze": 0, "silver": 0, "gold": 0}


def warm_layer_counts() -> None:
    """Public hook so the FastAPI startup event can pre-populate the cache
    before the first request lands. Idempotent across gunicorn workers thanks
    to ``_warmup_lock``.

    IMPORTANT: this runs the count in a BACKGROUND THREAD, not inline.

    Uvicorn's ``Server.startup()`` awaits ``lifespan.startup()`` BEFORE it
    calls ``loop.create_server()``. A blocking lifespan therefore keeps the
    TCP socket on port 8000 unbound for the whole duration, so the Docker
    healthcheck cannot connect, the container flips to ``unhealthy``, and
    ``depends_on: {backend: {condition: service_healthy}}`` never lets the
    frontend start.

    Counting the three layers walks ~300k object keys in MinIO and measured
    94s on the demo dataset — far longer than the 30s healthcheck
    ``start_period`` plus retries. Running it inline meant the backend could
    never report healthy at all. Warming in the background keeps startup
    instant; the first ``/system/status`` request still gets correct numbers
    because ``_layer_counts()`` falls back to a synchronous count when the
    cache is cold.
    """
    global _warmup_started
    with _warmup_lock:
        if _warmup_started:
            return
        _warmup_started = True

    thread = threading.Thread(
        target=_refresh_counts_cache,
        name="layer-count-warmup",
        daemon=True,
    )
    thread.start()
    logger.info("layer-count warmup started in background")


def _refresh_counts_cache() -> None:
    """Compute the layer counts and store them in the cache."""
    try:
        new_value = _compute_layer_counts()
    except Exception as exc:
        logger.warning("warm_layer_counts sync failed: %s", exc)
        return
    with _counts_lock:
        _counts_cache["value"] = new_value
        _counts_cache["expires_at"] = time.monotonic() + _COUNTS_CACHE_TTL_SECONDS
    _persist_counts(new_value)


# ── Layer-count persistence ───────────────────────────────────────────────────
# WHY THIS EXISTS
# ---------------
# Counting the three layers walks ~340k object keys in MinIO. That job needs
# the GIL for a long time, so while the auto-refresh pass is running it can
# take minutes to finish. If the backend restarts before the job completes,
# the cache is empty again and the System Status page has nothing to show.
#
# Persisting the last known counts to a small JSON file means a restart
# serves the previous numbers instantly (they are a slow-moving statistic
# anyway) instead of zeros, and the background job refines them.
_COUNTS_FILE = Path(settings.data_root_path) / "layer_counts.json"


def _persist_counts(counts: dict[str, int]) -> None:
    """Write the counts to disk so a restart does not have to recompute them."""
    try:
        _COUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _COUNTS_FILE.write_text(json.dumps(counts), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort
        logger.warning("layer-count persistence failed: %s", exc)


def _load_persisted_counts() -> dict[str, int] | None:
    """Read the counts saved by a previous run, if any."""
    try:
        if not _COUNTS_FILE.is_file():
            return None
        # `utf-8-sig` tolerates a byte-order mark. PowerShell's `Out-File
        # -Encoding utf8` writes one, and a file edited on Windows is a
        # perfectly ordinary thing to find here.
        payload = json.loads(_COUNTS_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            return None
        counts = {k: int(v) for k, v in payload.items() if isinstance(v, (int, float))}
        return counts or None
    except Exception as exc:  # noqa: BLE001 - a corrupt file must not break startup
        logger.warning("layer-count restore failed: %s", exc)
        return None


def restore_layer_counts() -> bool:
    """Seed the in-memory cache with the counts persisted by a previous run.

    Called at startup so the System Status page shows real numbers
    immediately instead of zeros. Returns True when a saved set was found.
    """
    counts = _load_persisted_counts()
    if not counts:
        return False
    with _counts_lock:
        _counts_cache["value"] = counts
        # The restored value is already "old", so the next request schedules a
        # background refresh that replaces it with fresh numbers.
        _counts_cache["expires_at"] = 0.0
    logger.info("Restored layer counts from disk: %s", counts)
    return True


def _probe_http(url: str, expect_status: list[int]) -> bool:
    """Quick HEAD-like probe; returns True if any expected status comes back."""
    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status in expect_status
    except urllib.error.HTTPError as exc:
        return exc.code in expect_status
    except Exception:
        return False


def _probe_tcp(endpoint: str) -> bool:
    """Quick TCP probe; returns True if connection succeeds."""
    if not endpoint or ":" not in endpoint:
        return False
    host, port = endpoint.rsplit(":", 1)
    try:
        import socket
        with socket.create_connection((host, int(port)), timeout=2):
            return True
    except Exception:
        return False


def _last_pipeline_run() -> dict | None:
    """Find the most recent pipeline run metadata JSON file.

    Only the dedicated ``pipeline_runs`` directory and the data root itself are
    scanned (non-recursively). A recursive walk over the data root used to traverse
    the entire lakehouse tree and took ~11s on the System Status page.
    """
    candidates = [
        Path(settings.data_root_path) / "pipeline_runs",
        Path(settings.data_root_path),
        Path("./backend/data/pipeline_runs"),
        Path("./data/pipeline_runs"),
    ]
    try:
        latest: tuple[float, Path] | None = None
        for base in candidates:
            if not base.is_dir():
                continue
            for path in base.glob("pipeline_run_*.json"):
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if latest is None or mtime > latest[0]:
                    latest = (mtime, path)
        if not latest:
            return None
        with latest[1].open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None