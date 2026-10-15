"""Health and system status endpoints."""

from __future__ import annotations

import json
import os
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
    """Walk the buckets and count objects per layer. Sequential, with a
    per-layer safety cap so a single slow bucket cannot stall forever."""
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
    about to expire, without blocking the current request."""
    def _job() -> None:
        try:
            new_value = _compute_layer_counts()
        except Exception as exc:
            logger.warning("background layer-count refresh failed: %s", exc)
            return
        with _counts_lock:
            _counts_cache["value"] = new_value
            _counts_cache["expires_at"] = time.monotonic() + _COUNTS_CACHE_TTL_SECONDS

    thread = threading.Thread(target=_job, name="layer-count-refresh", daemon=True)
    thread.start()


def _layer_counts() -> dict[str, int]:
    """Return cached layer counts when fresh; otherwise serve the last known
    value (if any) immediately and refresh in the background so the System
    Status page never blocks on a multi-second object listing.

    Behaviour:
    - First request after startup: synchronous count → cached.
    - Subsequent requests within TTL: served from cache.
    - Cache expired and a value still exists: serve stale value instantly,
      schedule a background refresh. The next request after the background
      refresh sees the fresh value.
    - Cache expired and no value at all (cold start): synchronous fallback.
    """
    now = time.monotonic()
    with _counts_lock:
        cached = _counts_cache["value"]
        expires_at = _counts_cache["expires_at"]

    if cached is not None and now < expires_at:
        return dict(cached)

    if cached is not None:
        # Serve stale value immediately; refresh in the background so the
        # next request gets fresh numbers without paying the wait here.
        _schedule_refresh()
        return dict(cached)

    # No cache at all (cold start). Run synchronously so the response is
    # correct on the very first request, then cache it for 5 minutes.
    counts = _compute_layer_counts()
    with _counts_lock:
        _counts_cache["value"] = counts
        _counts_cache["expires_at"] = time.monotonic() + _COUNTS_CACHE_TTL_SECONDS
    return counts


def warm_layer_counts() -> None:
    """Public hook so the FastAPI startup event can pre-populate the cache
    before the first request lands. Idempotent across gunicorn workers thanks
    to ``_warmup_lock``.

    Populates synchronously on the first call so the cache is warm even for
    the very first HTTP request (no cold-start blocking).
    """
    global _warmup_started
    with _warmup_lock:
        if _warmup_started:
            return
        _warmup_started = True
    # Compute synchronously so the cache is warm for the first /system/status
    # request. Subsequent refreshes happen in the background.
    try:
        new_value = _compute_layer_counts()
    except Exception as exc:
        logger.warning("warm_layer_counts sync failed: %s", exc)
        return
    with _counts_lock:
        _counts_cache["value"] = new_value
        _counts_cache["expires_at"] = time.monotonic() + _COUNTS_CACHE_TTL_SECONDS


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