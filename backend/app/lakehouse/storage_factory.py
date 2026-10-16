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


def get_storage_backend(refresh: bool = False) -> StorageBackend:
    """Return MinIO storage when configured and healthy, otherwise local files.

    Result is cached after the first successful resolution. Pass ``refresh=True``
    to force a re-probe (used by tests and by the admin reset flow).
    """
    global _cached_backend
    if _cached_backend is not None and not refresh:
        return _cached_backend

    backend: StorageBackend | None = None
    if settings.storage_backend == "minio":
        # Retry the whole init flow a few times. The MinIO container can
        # still be pre-flighting its data drive when the backend boots, so
        # the first 1-2 attempts are expected to fail with ConnectionError
        # or timeout. We give it up to ~30s before falling back to local.
        import time

        from app.lakehouse.minio_storage import MinioStorageBackend

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                candidate = MinioStorageBackend()
                health = candidate.health()
                if health.get("available"):
                    logger.info("Using MinIO storage backend.")
                    backend = candidate
                    break
                last_error = Exception(f"health check returned {health}")
            except Exception as exc:
                last_error = exc
            if attempt < 2:
                wait = 5 + attempt * 5  # 5, 10 seconds
                logger.warning(
                    "MinIO init attempt %d/3 failed (%s); retrying in %ds",
                    attempt + 1,
                    last_error,
                    wait,
                )
                time.sleep(wait)
        if backend is None and last_error is not None:
            logger.warning(
                "MinIO initialization failed after 3 attempts (%s). Falling back to local storage.",
                last_error,
            )

    if backend is None:
        logger.info("Using local filesystem storage backend.")
        backend = LocalStorageBackend()

    _cached_backend = backend
    return backend


def reset_storage_backend_cache() -> None:
    """Drop the cached backend so the next call re-probes MinIO."""
    global _cached_backend
    _cached_backend = None
