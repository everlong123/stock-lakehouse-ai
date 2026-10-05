"""Health and system status endpoints."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
    if provider == "gemini" and settings.gemini_api_key.strip():
        agent_status = "gemini_free"
    elif settings.gemini_api_key.strip():
        agent_status = "gemini_free"
    elif settings.openai_api_key.strip():
        agent_status = "llm_ready"
    elif provider == "local" or not settings.openai_api_key.strip():
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


def _layer_counts() -> dict[str, int]:
    """Count objects per layer concurrently, tolerating individual failures."""
    layers = {
        "bronze": BronzeLayer,
        "silver": SilverLayer,
        "gold": GoldLayer,
    }
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=len(layers)) as pool:
        futures = {name: pool.submit(cls().record_count) for name, cls in layers.items()}
        for name, future in futures.items():
            try:
                counts[name] = int(future.result(timeout=20))
            except Exception as exc:
                logger.warning("record_count failed for %s: %s", name, exc)
                counts[name] = -1
    return counts


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