"""MinIO object storage backend."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import pandas as pd

from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.logging_config import get_logger
from app.lakehouse.storage_base import (
    StorageBackend,
    dataframe_to_parquet_bytes,
    parquet_bytes_to_dataframe,
)

logger = get_logger(__name__)

LAYER_BUCKETS = {
    "bronze": settings.minio_bucket_bronze,
    "silver": settings.minio_bucket_silver,
    "gold": settings.minio_bucket_gold,
    "models": settings.minio_bucket_models,
    "backtests": settings.minio_bucket_backtests,
    "quality": settings.minio_bucket_silver,
    "silver_news": settings.minio_bucket_silver_news,
    "silver_fundamentals": settings.minio_bucket_silver_fundamentals,
    "gold_features": settings.minio_bucket_gold_features,
}

# How many partition files are downloaded in parallel by `read_prefix`.
# 8 keeps MinIO (single-node, local disk) comfortably busy without
# exhausting its connection pool.
# How many partitions to read in parallel.
#
# WHY 6 AND NOT 8: the refresh pass writes ~90 partition objects per minute,
# and MinIO resets connections when it is overloaded. Reading with 8 threads
# while 3 rebuild workers write 8 partitions each (24 concurrent writes)
# pushed the server over the edge - measured 22 connection resets during a
# 30-symbol browse on 2026-11-03.
#
# 6 keeps the read path fast (the partitions are small and latency-bound)
# while leaving the server room to accept the writes.
_READ_CONCURRENCY = int(os.getenv("MINIO_READ_CONCURRENCY", "6"))

# How many times a single partition read is retried after the server
# dropped the connection.
#
# WHY: the auto-refresh pass writes ~90 partition objects per minute, and
# that is enough to make MinIO reset connections. urllib3's own retry only
# covers status codes, so a transport-level ConnectionResetError used to
# fail the whole symbol read - and the connect timeout made each failure
# cost 10-30s. Measured 22 resets during a 30-symbol browse.
_READ_RETRIES = 3


def _is_connection_reset(exc: Exception) -> bool:
    """True when the failure was a dropped connection rather than a real error."""
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "connectionreseterror",
            "connection reset",
            "forcibly closed",
            "connection aborted",
            "remotedisconnected",
            "broken pipe",
            "connectionerror",
        )
    )


class MinioStorageBackend(StorageBackend):
    """Store lakehouse datasets in MinIO buckets."""

    backend_name = "minio"

    def __init__(self) -> None:
        try:
            from minio import Minio
        except ImportError as exc:
            raise StorageError("minio package is not installed.") from exc
        import urllib3

        # Larger pool so list_objects on different buckets can run in parallel
        # (the System Status page counts all 3 layers concurrently).
        #
        # The pool size has to cover the parallelism of the writers, not just
        # the readers. A rebuild worker touches Silver and Gold objects
        # concurrently, and with 16 rebuild workers a pool of 10 made every
        # worker log "Connection pool is full, discarding connection" - the
        # surplus connections were being thrown away and re-opened, which
        # turned into constant TCP churn and made the rebuild crawl.
        #
        # 64 is comfortably above the worst case (16 workers x ~3 concurrent
        # requests) while still leaving room for the read paths.
        #
        # The timeout is split: reads are quick (a parquet object is small), but
        # a WRITE of a month partition has to go through MinIO's disk while 12
        # other workers do the same. At 15s the write path started timing out
        # with "Read timed out" and the symbol was left half-rebuilt, so the
        # connect/read budget is generous enough to ride out that contention.
        #
        # The CONNECT timeout is short on purpose: MinIO runs on the same
        # host (127.0.0.1), so a fresh TCP connection takes milliseconds. A
        # 10s connect budget meant that every dropped connection (which the
        # refresh pass triggers regularly) stalled the read for 10s before
        # the retry even started - and with three attempts that turned one
        # unlucky partition into a 30s hang. 3s is still ~1000x the real
        # connect time and fails fast enough to matter.
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=3, read=60),
            maxsize=64,
            block=True,
            retries=urllib3.util.retry.Retry(total=1, status_forcelist=(502, 503, 504)),
        )
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            http_client=http_client,
        )
        self._ensure_buckets()

    def _ensure_buckets(self) -> None:
        # Retry briefly: when the backend boots at the same time as the
        # MinIO container, MinIO can still be starting its data drive
        # pre-flight and refuses the first connections. Five attempts over
        # ~30s covers that window without holding up startup forever if
        # MinIO is genuinely down.
        import time

        last_error: Exception | None = None
        for attempt in range(5):
            try:
                for bucket in set(LAYER_BUCKETS.values()):
                    if not self.client.bucket_exists(bucket):
                        self.client.make_bucket(bucket)
                        logger.info("Created MinIO bucket %s", bucket)
                return
            except Exception as exc:
                last_error = exc
                if attempt < 4:
                    wait = 2 + attempt * 2  # 2, 4, 6, 8 seconds
                    logger.warning(
                        "MinIO ensure_buckets attempt %d/5 failed (%s); retrying in %ds",
                        attempt + 1,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
        raise StorageError(
            f"Cannot initialize MinIO buckets after 5 attempts: {last_error}"
        ) from last_error

    def _bucket(self, layer: str) -> str:
        if layer not in LAYER_BUCKETS:
            raise StorageError(f"Unknown lakehouse layer: {layer}")
        return LAYER_BUCKETS[layer]

    def write_parquet(self, layer: str, relative_path: str, frame: pd.DataFrame) -> str:
        payload = dataframe_to_parquet_bytes(frame)
        return self._put_bytes(layer, relative_path, payload, "application/octet-stream")

    def read_parquet(self, layer: str, relative_path: str) -> pd.DataFrame:
        payload = self._get_bytes(layer, relative_path)
        return parquet_bytes_to_dataframe(payload)

    def read_prefix(self, layer: str, prefix: str) -> pd.DataFrame:
        keys = [key for key in self.list_objects(layer, prefix) if key.endswith(".parquet")]
        if not keys:
            return pd.DataFrame()
        # Download the partitions CONCURRENTLY.
        #
        # WHY: a long-history symbol (e.g. AAPL, 2016-2026) is split into ~120
        # monthly parquet partitions. Reading them one after another meant ~120
        # sequential MinIO round-trips, which took 5s when idle and >100s while
        # the auto-refresh pass was hammering the same MinIO instance — long
        # enough for the frontend's 90s axios timeout to fire and the dashboard
        # to show "Yêu cầu mất quá lâu".
        #
        # The reads are independent and side-effect free, so a thread pool is
        # the right tool: it cuts the wall-clock to a handful of round-trips
        # without changing the result. The row order is restored afterwards so
        # the concatenated frame keeps the chronological order of `keys`.
        frames: list[pd.DataFrame | None] = [None] * len(keys)
        with ThreadPoolExecutor(max_workers=_READ_CONCURRENCY) as pool:
            futures = {
                pool.submit(self.read_parquet, layer, key): idx
                for idx, key in enumerate(keys)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    frames[idx] = future.result()
                except Exception as exc:  # noqa: BLE001 - one bad partition must not kill the read
                    logger.warning("Failed to read partition %s: %s", keys[idx], exc)
                    frames[idx] = None
        usable = [f for f in frames if f is not None and not f.empty]
        if not usable:
            return pd.DataFrame()
        return pd.concat(usable, ignore_index=True)

    def list_objects(self, layer: str, prefix: str = "") -> list[str]:
        bucket = self._bucket(layer)
        try:
            objects = self.client.list_objects(bucket, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        except Exception as exc:
            raise StorageError(f"MinIO list failed: {exc}") from exc

    def exists(self, layer: str, relative_path: str) -> bool:
        bucket = self._bucket(layer)
        try:
            self.client.stat_object(bucket, relative_path)
            return True
        except Exception:
            return False

    def write_json(self, layer: str, relative_path: str, payload: dict) -> str:
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        return self._put_bytes(layer, relative_path, body, "application/json")

    def read_json(self, layer: str, relative_path: str) -> dict:
        payload = self._get_bytes(layer, relative_path)
        return json.loads(payload.decode("utf-8"))

    def count_objects(self, layer: str, prefix: str = "") -> int:
        return len(self.list_objects(layer, prefix))

    def health(self) -> dict[str, str | bool]:
        try:
            self.client.list_buckets()
            return {"backend": self.backend_name, "available": True}
        except Exception as exc:
            logger.warning("MinIO health check failed: %s", exc)
            return {"backend": self.backend_name, "available": False}

    def _put_bytes(self, layer: str, relative_path: str, payload: bytes, content_type: str) -> str:
        bucket = self._bucket(layer)
        try:
            self.client.put_object(
                bucket,
                relative_path,
                BytesIO(payload),
                length=len(payload),
                content_type=content_type,
            )
        except Exception as exc:
            raise StorageError(f"MinIO put failed for {relative_path}: {exc}") from exc
        return f"{bucket}/{relative_path}"

    def _get_bytes(self, layer: str, relative_path: str) -> bytes:
        bucket = self._bucket(layer)
        last_exc: Exception | None = None
        # Retry a read that the server dropped mid-flight.
        #
        # WHY: MinIO resets connections when it is overloaded, and the
        # refresh pass writes ~90 partition objects per minute, which is
        # enough to trip it. urllib3's own retry only covers STATUS codes
        # (502/503/504) - a ConnectionResetError is a transport error and
        # was raised straight through to the caller, which failed the whole
        # symbol read.
        #
        # Measured on 2026-11-03: 22 connection resets during a 30-symbol
        # browse, and the read that hit one stalled for 30s (the connect
        # timeout) before failing the symbol outright.
        for attempt in range(1, _READ_RETRIES + 1):
            try:
                response = self.client.get_object(bucket, relative_path)
                try:
                    return response.read()
                finally:
                    response.close()
                    response.release_conn()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt == _READ_RETRIES or not _is_connection_reset(exc):
                    break
                logger.debug(
                    "MinIO read %s reset (attempt %d/%d), retrying",
                    relative_path,
                    attempt,
                    _READ_RETRIES,
                )
        raise StorageError(f"MinIO get failed for {relative_path}: {last_exc}") from last_exc
