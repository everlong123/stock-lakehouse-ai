"""Storage backend factory with local fallback when MinIO is unavailable.

The backend is cached as a process-wide singleton. Re-probing MinIO health on every
call added a network round-trip to each lakehouse read (and the System Status page
probes four times per request), which made list operations crawl.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging_config import get_logger
from app.lakehouse.local_storage import LocalStorageBackend
from app.lakehouse.storage_base import StorageBackend

logger = get_logger(__name__)

_cached_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Return MinIO storage when configured and healthy, otherwise local files.

    Result is cached after the first successful resolution. Pass ``refresh=True``
    to force a re-probe (used by tests and by the admin reset flow).
    """
    global _cached_backend
    if _cached_backend is not None:
        return _cached_backend

    backend: StorageBackend | None = None
    if settings.storage_backend == "minio":
        try:
            from app.lakehouse.minio_storage import MinioStorageBackend

            candidate = MinioStorageBackend()
            health = candidate.health()
            if health.get("available"):
                logger.info("Using MinIO storage backend.")
                backend = candidate
            else:
                logger.warning("MinIO is configured but unavailable. Falling back to local storage.")
        except Exception as exc:
            logger.warning("MinIO initialization failed (%s). Falling back to local storage.", exc)

    if backend is None:
        logger.info("Using local filesystem storage backend.")
        backend = LocalStorageBackend()

    _cached_backend = backend
    return backend


def reset_storage_backend_cache() -> None:
    """Drop the cached backend so the next call re-probes MinIO."""
    global _cached_backend
    _cached_backend = None
