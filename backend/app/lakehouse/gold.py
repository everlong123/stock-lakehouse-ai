"""Gold layer: analytics-ready features and targets without look-ahead leakage."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.core.exceptions import DataValidationError
from app.core.logging_config import get_logger
from app.features.feature_engineering import build_gold_features
from app.lakehouse.bronze import symbol_prefix
from app.lakehouse import frame_cache
from app.lakehouse.parquet_manager import partitions_from, split_by_partition
from app.lakehouse.parallel_write import write_partitions_concurrently as _write_partitions_concurrently
from app.lakehouse.spark_session import get_spark_session, spark_enabled
from app.lakehouse.session import slice_window
from app.lakehouse.storage_base import StorageBackend
from app.lakehouse.storage_factory import get_storage_backend

logger = get_logger(__name__)


class GoldLayer:
    """Feature and target zone consumed by TA, ML, DL, backtesting, and dashboards."""

    layer_name = "gold"

    def __init__(self, storage: StorageBackend | None = None) -> None:
        self.storage = storage or get_storage_backend()

    def transform(self, silver_frame: pd.DataFrame) -> pd.DataFrame:
        """Build Gold features. Spark is used for column-level transforms when enabled."""
        if silver_frame.empty:
            raise DataValidationError("Silver frame is empty; cannot build Gold.")
        spark = get_spark_session() if spark_enabled() else None
        if spark is not None:
            return self._transform_spark(silver_frame, spark)
        return build_gold_features(silver_frame)

    def write(self, gold_frame: pd.DataFrame, changed_since: date | None = None) -> dict:
        """Write Gold partitions for the symbols present in the frame.

        The partitions are written CONCURRENTLY - a 10-year daily symbol has
        ~121 monthly partitions, and writing them serially cost ~1.5s of
        MinIO round-trips per symbol. See `app/lakehouse/parallel_write.py`.

        WHY `changed_since` MATTERS
        --------------------------
        Every Gold feature is causal - it looks BACKWARD only. A rebuild
        triggered by a new bar at the end of the history therefore
        produces exactly the same rows for every earlier session, and
        writing their partitions again is pure waste: 2.7 s of round-trips
        per symbol, measured 14/11/2026, for content that did not
        change.

        `changed_since` is the earliest session whose content may have
        changed. Only the partitions from that month onwards are
        written. Passing None writes everything, which is what a full
        backfill must do.

        The cached frame of every written symbol is dropped afterwards:
        the stored data has just changed, so the cached copy is stale.
        """
        partitions = split_by_partition(gold_frame)
        selected = partitions_from(partitions, changed_since)
        paths = _write_partitions_concurrently(self.storage, self.layer_name, selected)
        logger.info(
            "Gold write complete: %s rows, %s partitions (%s of %s rewritten)",
            len(gold_frame),
            len(paths),
            len(selected),
            len(partitions),
        )
        self._invalidate_written(gold_frame)
        return {"paths": paths, "records": int(len(gold_frame))}

    def _invalidate_written(self, gold_frame: pd.DataFrame) -> None:
        """Drop the cached frames of the symbols this write touched."""
        if "symbol" not in gold_frame.columns:
            return
        for symbol in gold_frame["symbol"].dropna().unique():
            self.invalidate_cache(str(symbol))

    def read(self, symbol: str) -> pd.DataFrame:
        """The symbol's Gold rows, through the shared frame cache.

        WHY THE CACHE IS HERE
        ---------------------
        A 10-year daily symbol is stored as ~121 monthly parquet objects.
        Reading them all from MinIO costs ~0.5 s (measured 13/11/2026).
        The nightly universe pass reads 973 symbols, so the reads are
        ~90% of the pass's cost.

        The cache turns the repeated reads into a memory lookup: the
        forecast pass, the scoring pass and the calendar all work on
        the SAME frame. The auto-refresh pass invalidates the entry
        when it rewrites a symbol, so a fresh frame replaces a stale one
        at once rather than waiting for the TTL.
        """
        cached = frame_cache.get_cached(self.layer_name, symbol)
        if cached is not None:
            return cached

        frame = self.storage.read_prefix(self.layer_name, symbol_prefix(symbol))
        if frame.empty:
            return frame
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.loc[:, ~frame.columns.duplicated()]
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        frame_cache.put_cached(self.layer_name, symbol, frame)
        return frame

    def read_window(
        self,
        symbol: str,
        since: date | None = None,
        until: date | None = None,
    ) -> pd.DataFrame:
        """The symbol's Gold rows inside a date window.

        WHY THIS EXISTS
        ---------------
        A ten-year daily symbol is stored as ~121 monthly partitions. A
        request for "the last six months" needs six of them, and the
        other 115 were downloaded, parsed and thrown away - so the
        request cost was set by the symbol's HISTORY rather than by the
        window the caller asked for.

        A WINDOWED READ IS NEVER CACHED. The cache holds a symbol's
        COMPLETE history, and storing a partial frame under the symbol's
        key would make every later reader believe the symbol has only
        the rows of that window. The windowed frame is already cheap:
        it is a handful of partitions, not a hundred.
        """
        if since is None and until is None:
            return self.read(symbol)

        # The complete frame, when it is already in memory, answers the
        # window without touching storage at all.
        cached = frame_cache.get_cached(self.layer_name, symbol)
        if cached is not None:
            return slice_window(cached, since, until)

        frame = self.storage.read_prefix_window(
            self.layer_name, symbol_prefix(symbol), since=since, until=until
        )
        if frame.empty:
            return frame
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.loc[:, ~frame.columns.duplicated()]
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        return slice_window(frame, since, until)

    def read_newest(self, symbol: str) -> pd.DataFrame:
        """The symbol's NEWEST stored Gold rows, without reading its history.

        WHY THIS EXISTS
        ---------------
        A ten-year daily symbol is stored as ~121 monthly partitions. A
        caller that only wants the newest bar - the market tape, the
        latest-price endpoint - was downloading all 121 of them.

        Measured on 14/11/2026: the ten-symbol tape took 11.7 s cold
        because each quote pulled the symbol's whole history. Reading
        the newest partition instead costs one listing plus one object
        download.

        The result is the SAME stored rows: the newest partition holds
        the symbol's most recent sessions, and nothing is recomputed
        or invented.
        """
        frame = self.storage.read_newest_partition(self.layer_name, symbol_prefix(symbol))
        if frame.empty:
            return frame
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.loc[:, ~frame.columns.duplicated()]
        return frame.sort_values("timestamp").reset_index(drop=True)

    def invalidate_cache(self, symbol: str) -> None:
        """Drop the symbol's cached frame after it was rewritten."""
        frame_cache.invalidate_cached(self.layer_name, symbol)

    def record_count(self, symbol: str | None = None) -> int:
        """Count stored objects without downloading/parsing parquet payloads."""
        prefix = symbol_prefix(symbol) if symbol else ""
        return int(self.storage.count_objects(self.layer_name, prefix))

    def latest_timestamp(self, symbol: str) -> pd.Timestamp | None:
        """Return the newest stored timestamp for ``symbol`` without a full read.

        Mirrors `BronzeLayer.latest_timestamp`. The auto-refresh uses this to decide
        whether to rebuild Silver/Gold when Bronze has not received new rows but the
        Silver/Gold watermark is nevertheless behind Bronze's.
        """
        keys = self.storage.list_objects(self.layer_name, symbol_prefix(symbol))
        data_keys = [k for k in keys if k.endswith(".parquet")]
        if not data_keys:
            return None
        for key in sorted(data_keys, reverse=True)[:2]:
            frame = self.storage.read_parquet(self.layer_name, key)
            if frame is None or frame.empty or "timestamp" not in frame.columns:
                continue
            stamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dropna()
            if not stamps.empty:
                return stamps.max()
        return None

    def _transform_spark(self, frame: pd.DataFrame, spark) -> pd.DataFrame:
        """Apply Spark numeric casting then reuse Pandas feature builder for window features."""
        from pyspark.sql import functions as F
        from pyspark.sql.types import DoubleType, StringType, TimestampType

        sdf = spark.createDataFrame(frame)
        sdf = sdf.withColumn("symbol", F.upper(F.col("symbol").cast(StringType())))
        sdf = sdf.withColumn("timestamp", F.col("timestamp").cast(TimestampType()))
        for col in ["open", "high", "low", "close", "adj_close", "volume"]:
            sdf = sdf.withColumn(col, F.col(col).cast(DoubleType()))
        pandas_frame = sdf.orderBy("symbol", "timestamp").toPandas()
        pandas_frame["timestamp"] = pd.to_datetime(pandas_frame["timestamp"], utc=True)
        return build_gold_features(pandas_frame)
