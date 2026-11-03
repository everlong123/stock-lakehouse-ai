"""Bronze layer: raw ingested OHLCV close to the source schema."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.core.constants import OHLCV_COLUMNS
from app.core.exceptions import DataValidationError, StorageError
from app.core.logging_config import get_logger
from app.lakehouse.dedupe import dedupe_same_bars
from app.lakehouse.parquet_manager import split_by_partition
from app.lakehouse.plausibility import screen_batch
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


def symbol_prefix(symbol: str) -> str:
    """Return the exact object prefix for one symbol's partitions.

    The trailing slash matters. Without it, ``symbol=M`` also matches
    ``symbol=MA/``, ``symbol=MCD/``, ``symbol=META/`` ... so reading "M"
    silently concatenated 51 tickers (5,801 partitions, 121,913 rows) and
    every downstream consumer - API, charts, indicators - plotted the blend.
    Always terminate the prefix at the directory boundary.
    """
    return f"symbol={symbol.upper()}/"


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

    def _reference_prices(self, frame: pd.DataFrame) -> dict[str, float]:
        """Median recent close per symbol, read from the newest stored partition.

        Only the newest partition is read, so this stays cheap on a lakehouse
        with ~100 symbols: one object per symbol rather than the full history.
        A symbol with no stored history is omitted, and the screen then applies
        only its self-contained checks - degrading safely instead of guessing.
        """
        if frame.empty or "symbol" not in frame.columns:
            return {}

        references: dict[str, float] = {}
        for symbol in sorted(set(frame["symbol"].astype(str).str.upper())):
            try:
                keys = [
                    k
                    for k in self.storage.list_objects(self.layer_name, symbol_prefix(symbol))
                    if k.endswith(".parquet")
                ]
            except Exception as exc:  # noqa: BLE001 - never block ingestion
                logger.debug("Reference price lookup failed for %s: %s", symbol, exc)
                continue
            if not keys:
                continue
            try:
                stored = self.storage.read_parquet(self.layer_name, sorted(keys, reverse=True)[0])
            except Exception as exc:  # noqa: BLE001
                logger.debug("Reference partition unreadable for %s: %s", symbol, exc)
                continue
            if stored is None or stored.empty or "close" not in stored.columns:
                continue
            closes = pd.to_numeric(stored["close"], errors="coerce").dropna()
            closes = closes[closes > 0]
            if closes.empty:
                continue
            references[symbol] = float(closes.median())
        return references

    def append(self, frame: pd.DataFrame, lineage: dict | None = None) -> dict:
        """Append rows to partitioned Parquet files. Duplicates are counted, not silently ignored."""
        if frame.empty:
            raise DataValidationError("Cannot write empty frame to Bronze.")
        clean = self.validate_schema(frame)
        clean["ingestion_time"] = clean["ingestion_time"].fillna(pd.Timestamp.now(tz="UTC"))

        # Reject rows that cannot be real market data BEFORE they reach
        # storage. A parser bug in a streaming publisher otherwise becomes
        # permanent corruption: vn_ws once wrote VCB bars stamped 1970-01-10
        # with close=56.9 against a true price of 56,600. Nothing downstream
        # could detect that later, and every rolling indicator over the head
        # of the series would be poisoned.
        #
        # The per-symbol price level is fetched from existing storage so a
        # unit error (a VND quote divided by 1000) is caught even when the
        # timestamp looks plausible. It is read from the symbol's own history
        # rather than a static table, so a symbol whose price genuinely moved
        # still passes.
        clean, plausibility = screen_batch(
            clean, reference_prices=self._reference_prices(clean)
        )
        if plausibility.has_rejections:
            self.storage.write_json(
                self.layer_name,
                "_quality/rejected_rows.json",
                {
                    "stage": "plausibility",
                    "ingestion_time": datetime.now(timezone.utc).isoformat(),
                    "report": plausibility.to_dict(),
                    "samples": plausibility.samples,
                    "lineage": lineage or {},
                },
            )
        if clean.empty:
            raise DataValidationError(
                "All incoming rows failed the plausibility screen; nothing written."
            )

        partitions = split_by_partition(clean)
        written_paths: list[str] = []
        records_written = 0
        new_records = 0
        duplicate_count = 0
        for relative_path, group in partitions.items():
            existing = pd.DataFrame()
            if self.storage.exists(self.layer_name, relative_path):
                existing = self.storage.read_parquet(self.layer_name, relative_path)
            existing_count = len(existing)
            # Count duplicates on the COMBINED frame so we catch dups between
            # the incoming batch and existing storage, not just within the batch.
            combined = pd.concat([existing, group], ignore_index=True)
            before = len(combined)
            combined = combined.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
            # Two providers can describe the SAME session under different
            # timestamps (yfinance_eod stamps 04:00Z, yahoo_http 13:30Z), so
            # exact-timestamp dedupe is not enough: the second copy survives
            # and then occupies two slots in every rolling window downstream.
            # Dedupe again by price payload, which collapses a re-stamped bar
            # while preserving genuine intraday ticks (AAPL 2026-10-13 holds 13
            # real ticks whose prices differ).
            combined, same_bar_dropped = dedupe_same_bars(combined)
            dropped = before - len(combined)
            duplicate_count += int(dropped)
            path = self.storage.write_parquet(self.layer_name, relative_path, combined)
            written_paths.append(path)
            records_written += len(group)
            # Rows that are genuinely NEW to storage, i.e. the growth of the
            # partition after dedupe. This is NOT the same as
            # ``records_written`` (which counts the incoming batch, including
            # rows that were already stored and got deduped away).
            #
            # WHY this matters: the auto-refresh fetches with a 5-day overlap,
            # so most incoming batches are rows the lakehouse already holds.
            # Reporting those as "written" made the refresh believe every
            # symbol had new data and triggered a full Silver + Gold rebuild
            # for it — each rebuild re-reads and re-writes all ~121 monthly
            # partitions. That turned a cheap no-op pass into ~16s of
            # MinIO traffic per symbol and starved the HTTP read path, which
            # is what made the UI exceed its 90s timeout.
            new_records += max(0, len(combined) - existing_count)
            if same_bar_dropped:
                logger.info(
                    "Bronze dropped %s same-bar rows (re-stamped session) in %s",
                    same_bar_dropped,
                    relative_path,
                )
        metadata = {
            "layer": self.layer_name,
            "records_received": int(len(clean)),
            "records_written": records_written,
            "new_records": new_records,
            "duplicate_count": duplicate_count,
            "plausibility_rejected": int(plausibility.rejected_rows),
            "plausibility_reasons": dict(plausibility.reasons),
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
        frame = self.storage.read_prefix(self.layer_name, symbol_prefix(symbol))
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
        keys = self.storage.list_objects(self.layer_name, symbol_prefix(symbol))
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
        prefix = symbol_prefix(symbol) if symbol else ""
        return int(self.storage.count_objects(self.layer_name, prefix))
