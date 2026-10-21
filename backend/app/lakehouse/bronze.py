"""Bronze layer: raw ingested OHLCV close to the source schema."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.core.constants import OHLCV_COLUMNS
from app.core.exceptions import DataValidationError, StorageError
from app.core.logging_config import get_logger
from app.lakehouse.parquet_manager import split_by_partition
from app.lakehouse.storage_base import StorageBackend
from app.lakehouse.storage_factory import get_storage_backend

logger = get_logger(__name__)

BRONZE_SCHEMA = {
    "symbol": "string",
    "timestamp": "datetime64[ns, UTC]",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "adj_close": "float64",
    "volume": "float64",
    "source": "string",
    "ingestion_time": "datetime64[ns, UTC]",
}


class BronzeLayer:
    """Append-only raw lakehouse zone with partition, lineage, and duplicate checks."""

    layer_name = "bronze"

    def __init__(self, storage: StorageBackend | None = None) -> None:
        self.storage = storage or get_storage_backend()

    def validate_schema(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Ensure required columns exist and types are coercible."""
        missing = [col for col in OHLCV_COLUMNS if col not in frame.columns]
        if missing:
            raise DataValidationError(f"Bronze schema missing columns: {missing}")
        result = frame[OHLCV_COLUMNS].copy()
        result["symbol"] = result["symbol"].astype(str).str.upper()
        result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
        result["ingestion_time"] = pd.to_datetime(result["ingestion_time"], utc=True)
        for col in ["open", "high", "low", "close", "adj_close", "volume"]:
            result[col] = pd.to_numeric(result[col], errors="coerce")
        result["source"] = result["source"].astype(str)
        return result

    def append(self, frame: pd.DataFrame, lineage: dict | None = None) -> dict:
        """Append rows to partitioned Parquet files. Duplicates are counted, not silently ignored."""
        if frame.empty:
            raise DataValidationError("Cannot write empty frame to Bronze.")
        clean = self.validate_schema(frame)
        clean["ingestion_time"] = clean["ingestion_time"].fillna(pd.Timestamp.now(tz="UTC"))
        partitions = split_by_partition(clean)
        written_paths: list[str] = []
        records_written = 0
        duplicate_count = 0
        for relative_path, group in partitions.items():
            existing = pd.DataFrame()
            if self.storage.exists(self.layer_name, relative_path):
                existing = self.storage.read_parquet(self.layer_name, relative_path)
            # Count duplicates on the COMBINED frame so we catch dups between
            # the incoming batch and existing storage, not just within the batch.
            combined = pd.concat([existing, group], ignore_index=True)
            before = len(combined)
            combined = combined.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
            dropped = before - len(combined)
            duplicate_count += int(dropped)
            path = self.storage.write_parquet(self.layer_name, relative_path, combined)
            written_paths.append(path)
            records_written += len(group)
        metadata = {
            "layer": self.layer_name,
            "records_received": int(len(clean)),
            "records_written": records_written,
            "duplicate_count": duplicate_count,
            "partitions": list(partitions.keys()),
            "paths": written_paths,
            "lineage": lineage or {},
            "ingestion_time": datetime.now(timezone.utc).isoformat(),
            "storage_backend": self.storage.backend_name,
        }
        symbols = sorted(clean["symbol"].unique().tolist())
        for symbol in symbols:
            self.storage.write_json(
                self.layer_name,
                f"symbol={symbol}/_lineage.json",
                metadata,
            )
        logger.info(
            "Bronze append complete: received=%s duplicates=%s paths=%s",
            len(clean),
            duplicate_count,
            len(written_paths),
        )
        return metadata

    def read(self, symbol: str) -> pd.DataFrame:
        """Read all Bronze partitions for a symbol."""
        frame = self.storage.read_prefix(self.layer_name, f"symbol={symbol.upper()}")
        if frame.empty:
            return frame
        return self.validate_schema(frame).sort_values("timestamp").reset_index(drop=True)

    def latest_timestamp(self, symbol: str) -> pd.Timestamp | None:
        """Return the newest stored timestamp for ``symbol`` without a full read.

        `read()` pulls every year/month parquet partition (a 10-year daily
        ticker is ~120 objects) just so the caller can compute a watermark.
        The incremental refresh runs that for every symbol on every pass, which
        dominates the pass duration. Here we list the partition keys, sort them
        descending (they are `year=YYYY/month=MM/...` so lexicographic order is
        chronological), and fetch only the newest partition. Falls back to the
        previous month in case the last one is empty or missing.
        """
        keys = self.storage.list_objects(self.layer_name, f"symbol={symbol.upper()}/")
        # Drop metadata sidecars such as `_lineage.json`.
        data_keys = [k for k in keys if k.endswith(".parquet")]
        if not data_keys:
            return None
        # Month partitions are complete files; newest key = newest data. Reverse
        # the list so the caller stops as soon as it finds a populated one.
        for key in sorted(data_keys, reverse=True)[:2]:
            frame = self.storage.read_parquet(self.layer_name, key)
            if frame is None or frame.empty or "timestamp" not in frame.columns:
                continue
            stamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dropna()
            if not stamps.empty:
                return stamps.max()
        return None

    def record_count(self, symbol: str | None = None) -> int:
        """Count stored objects without downloading/parsing parquet payloads.

        Reading every partition just to call len() is prohibitively slow once the
        lakehouse holds hundreds of symbols, so we count keys in the bucket instead.
        """
        prefix = f"symbol={symbol.upper()}" if symbol else ""
        return int(self.storage.count_objects(self.layer_name, prefix))
