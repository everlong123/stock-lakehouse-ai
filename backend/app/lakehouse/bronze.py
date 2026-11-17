"""Bronze layer: raw ingested OHLCV close to the source schema."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from app.core.constants import OHLCV_COLUMNS
from app.core.exceptions import DataValidationError, StorageError
from app.core.logging_config import get_logger
from app.lakehouse.dedupe import dedupe_same_bars
from app.lakehouse.parquet_manager import split_by_partition
from app.lakehouse.session import newest_bar_session_close, slice_window
from app.lakehouse.plausibility import (
    PRICE_REFERENCE_SAMPLE,
    REFERENCE_PARTITION_SAMPLE,
    screen_batch,
)
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

    def _reference_prices(self, frame: pd.DataFrame) -> dict[str, dict[str, float]]:
        """Recent price LEVEL per symbol, read from the newest stored partitions.

        Only the newest partitions are read, so this stays cheap on a lakehouse
        with ~1000 symbols: a couple of objects per symbol rather than the
        full history. A symbol with no stored history is omitted, and the screen
        then applies only its self-contained checks - degrading safely instead
        of guessing.

        Each symbol maps to TWO numbers, because the two checks that consume
        this reference ask different questions:

          * ``floor``     - the LOW end of the recent range. Answers "is this
            symbol a cheap instrument?", which decides whether the absolute
            price floor of 0.5 may be relaxed.
          * ``magnitude`` - the MEDIAN of the recent range. Answers "is this
            price wildly far from where this symbol trades?", which is what
            catches a unit error.

        WHY THEY CANNOT BE THE SAME NUMBER
        ----------------------------------
        PARA is the concrete case for both directions.

        Its newest partition (2026-11) still holds a few pre-split bars
        around 2.72 next to the post-split ones, so the partition MEDIAN is
        ~2.21 while the symbol's real recent level is ~0.42. With 2.21 as
        the floor reference, the absolute floor of 0.5 stayed in force and
        the provider's genuine 0.425 bar was rejected as
        ``implausible_open``.

        That is a bar that can never be fixed. The screen compares the
        incoming row against the symbol's own stored level, and the stored
        level was the pre-split 4.251 - so the wrong value is always the
        reference and the right value always looks impossible. A 10:1 split
        on 2026-10-28 meant every earlier session had to be restated, and
        the restatement could not be ingested at all.

        But the LOW end cannot serve the magnitude check either. PARA traded
        near $102 in 2021 and near $0.47 in 2026, so its low end sits ~200x
        below its median. Using it for the magnitude check rejected the
        symbol's own 2021 history as ``price_magnitude`` - deleting real
        history to catch a rare unit bug.

        So the low end relaxes the floor for a genuinely cheap instrument,
        the median keeps the magnitude check honest, and a unit error is
        still caught because it is 1000x off - far outside both bands.
        """
        if frame.empty or "symbol" not in frame.columns:
            return {}

        references: dict[str, dict[str, float]] = {}
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

            closes: list[float] = []
            # The newest few partitions, so a symbol that just split keeps a
            # pre-split bar in the sample and drags the reference UP.
            for key in sorted(keys, reverse=True)[:REFERENCE_PARTITION_SAMPLE]:
                try:
                    stored = self.storage.read_parquet(self.layer_name, key)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Reference partition unreadable for %s: %s", key, exc)
                    continue
                if stored is None or stored.empty or "close" not in stored.columns:
                    continue
                values = pd.to_numeric(stored["close"], errors="coerce").dropna()
                closes.extend(float(v) for v in values[values > 0])
                if len(closes) >= PRICE_REFERENCE_SAMPLE:
                    break

            if not closes:
                continue
            references[symbol] = {
                "floor": min(closes),
                "magnitude": float(pd.Series(closes).median()),
            }
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
        updated_records = 0
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
            # Count how many rows this batch RESTATES: the (symbol, timestamp)
            # already exists in storage but carries a different price payload.
            #
            # WHY THIS IS COUNTED SEPARATELY FROM `new_records`
            # ---------------------------------------------------
            # `new_records` measures the GROWTH of the partition, so a provider
            # restatement - the provider revising a bar it had already
            # published - reports ZERO new rows. The auto-refresh used to
            # trigger the Silver/Gold rebuild on `new_rows > 0` alone, so a
            # restated bar was written to Bronze and then never propagated:
            # Silver and Gold kept the old close forever, and the web served
            # it forever. That is exactly what the verification pass flagged
            # as "RESTATED" on 30 European symbols (ADS.DE 2026-11-03 stored
            # 168.85 while the provider had revised it to 168.10).
            #
            # Counting restated rows separately lets the refresh rebuild on
            # "the stored value for this bar changed", not merely on "a new
            # bar appeared".
            updated_records += _count_restated_rows(existing, group)
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
            "updated_records": updated_records,
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

    def read_window(
        self,
        symbol: str,
        since: date | None = None,
        until: date | None = None,
    ) -> pd.DataFrame:
        """Read the Bronze partitions that can hold a date window.

        WHY THIS EXISTS
        ---------------
        A ten-year daily symbol is stored as ~121 monthly partitions. A
        request for "the last six months" needs six of them, and the
        other 115 were downloaded, parsed and discarded - so the request
        cost was set by the symbol's HISTORY rather than by the window
        the caller asked for.
        """
        if since is None and until is None:
            return self.read(symbol)
        frame = self.storage.read_prefix_window(
            self.layer_name, symbol_prefix(symbol), since=since, until=until
        )
        if frame.empty:
            return frame
        frame = self.validate_schema(frame)
        return slice_window(frame, since, until)

    def read_newest(self, symbol: str) -> pd.DataFrame:
        """The symbol's NEWEST stored Bronze rows, without reading its history.

        WHY THIS EXISTS
        ---------------
        A ten-year daily symbol is stored as ~121 monthly partitions. A
        caller that only wants the newest bar was downloading all 121
        of them. Measured on 14/11/2026: the ten-symbol tape took 11.7 s
        cold because each quote pulled the symbol's whole history.

        The result is the SAME stored rows - the newest partition holds
        the symbol's most recent sessions.
        """
        frame = self.storage.read_newest_partition(self.layer_name, symbol_prefix(symbol))
        if frame.empty:
            return frame
        return self.validate_schema(frame).sort_values("timestamp").reset_index(drop=True)

    def newest_session_close(self, symbol: str) -> tuple[object, float | None]:
        """Return ``(session_date, close)`` of the newest Bronze bar.

        WHY A DEDICATED READER
        ------------------------
        ``read()`` pulls every year/month parquet partition of the symbol (a
        10-year daily ticker is ~120 objects) just so the caller can look at
        the newest bar. The auto-refresh runs that for every symbol on every
        pass, which dominates the pass duration.

        This lists the partition keys, sorts them descending (they are
        ``year=YYYY/month=MM/...`` so lexicographic order is chronological) and
        fetches only the newest one, falling back to the previous month if the
        last one is empty.
        """
        keys = self.storage.list_objects(self.layer_name, symbol_prefix(symbol))
        data_keys = [k for k in keys if k.endswith(".parquet")]
        if not data_keys:
            return None, None
        for key in sorted(data_keys, reverse=True)[:2]:
            try:
                frame = self.storage.read_parquet(self.layer_name, key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Bronze newest_session_close read failed for %s: %s", symbol, exc)
                continue
            if frame is None or frame.empty:
                continue
            result = newest_bar_session_close(frame, symbol)
            if result[0] is not None:
                return result
        return None, None

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

    def latest_settled_timestamp(
        self,
        symbol: str,
        now: pd.Timestamp | None = None,
    ) -> pd.Timestamp | None:
        """Return the newest SETTLED bar's timestamp, ignoring a forming one.

        WHY THIS EXISTS
        ---------------
        A daily bar is stamped at the session OPEN, not at the session CLOSE.
        For an equity the open stamp is in the past by the time the day ends,
        so "the newest stored bar" is usually yesterday's - already settled.

        For a 24/7 instrument it is not. Crypto's daily bar is stamped at
        00:00Z of the day it covers, so the bar stored for TODAY is still
        forming: its close is whatever the price was at the last fetch. That
        bar is also the newest one, and it is always less than 24 hours old.

        The auto-refresh uses this timestamp as its watermark and skips any
        symbol whose newest bar is younger than ``AUTO_REFRESH_SKIP_IF_FRESH_HOURS``.
        With the forming bar counted, BTC-USD and ETH-USD were skipped on
        EVERY pass - and because the forming bar kept a fresh timestamp, the
        bar before it (the last genuinely settled day) was never re-fetched
        either. The measured result: the 2026-11-04 bar stayed frozen at the
        close it had mid-session (77,912 for BTC) while the provider had
        already settled it at 80,405.

        The fix is to treat a bar whose stamp is at or after today's UTC
        midnight as still forming, and to watermark on the last bar before it.
        The forming bar itself is still written on every pass - it is just not
        allowed to make the symbol look up to date.

        A symbol whose ONLY bar is today's forming bar has no settled bar at
        all; ``None`` is returned in that case, which makes the caller
        backfill rather than skip.
        """
        now = now or pd.Timestamp.now(tz="UTC")
        if now.tzinfo is None:
            now = now.tz_localize("UTC")

        keys = self.storage.list_objects(self.layer_name, symbol_prefix(symbol))
        data_keys = [k for k in keys if k.endswith(".parquet")]
        if not data_keys:
            return None

        # Midnight UTC today: anything stamped at or after this is a bar that
        # is still being formed.
        today_start = now.normalize()

        for key in sorted(data_keys, reverse=True)[:2]:
            frame = self.storage.read_parquet(self.layer_name, key)
            if frame is None or frame.empty or "timestamp" not in frame.columns:
                continue
            stamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dropna()
            if stamps.empty:
                continue
            settled = stamps[stamps < today_start]
            if not settled.empty:
                return settled.max()
            # Every bar in this partition is today's forming bar. Look at the
            # previous partition for the last settled one.
            continue
        return None

    def record_count(self, symbol: str | None = None) -> int:
        """Count stored objects without downloading/parsing parquet payloads.

        Reading every partition just to call len() is prohibitively slow once the
        lakehouse holds hundreds of symbols, so we count keys in the bucket instead.
        """
        prefix = symbol_prefix(symbol) if symbol else ""
        return int(self.storage.count_objects(self.layer_name, prefix))


# The price fields that identify a bar's content. A restatement is detected
# on these; `volume` alone moving is a revision of turnover, not of the bar.
_RESTATEMENT_KEY_COLUMNS = ("symbol", "timestamp")
_RESTATEMENT_PRICE_COLUMNS = ("open", "high", "low", "close")


def _count_restated_rows(existing: pd.DataFrame, incoming: pd.DataFrame) -> int:
    """Count incoming rows that RESTATE a bar already held in storage.

    A row is a restatement when the same ``(symbol, timestamp)`` already
    exists in ``existing`` but carries a different price payload. Such a row
    replaces the stored one during the dedupe (the incoming copy wins), so
    the partition does not GROW - which is why a plain row-count comparison
    cannot see it.

    WHY THIS EXISTS
    ---------------
    Providers revise history. Yahoo re-published ``ADS.DE`` 2026-11-03 with
    a close of 168.10 after having served 168.85. Bronze picked up the
    revision, but the partition row count did not change, so the auto-refresh
    concluded "nothing new for this symbol" and never rebuilt Silver/Gold.
    Silver and Gold therefore kept the old 168.85 and the web served it
    indefinitely - a real divergence between the lakehouse and the browser
    that no amount of re-fetching would fix.

    Returns 0 when either frame is empty or lacks the key columns.
    """
    if existing.empty or incoming.empty:
        return 0
    if not all(col in existing.columns for col in _RESTATEMENT_KEY_COLUMNS):
        return 0
    if not all(col in incoming.columns for col in _RESTATEMENT_KEY_COLUMNS):
        return 0

    price_columns = [
        col for col in _RESTATEMENT_PRICE_COLUMNS
        if col in existing.columns and col in incoming.columns
    ]
    if not price_columns:
        return 0

    old = existing.loc[:, list(_RESTATEMENT_KEY_COLUMNS) + price_columns].copy()
    new = incoming.loc[:, list(_RESTATEMENT_KEY_COLUMNS) + price_columns].copy()
    old["timestamp"] = pd.to_datetime(old["timestamp"], utc=True, errors="coerce")
    new["timestamp"] = pd.to_datetime(new["timestamp"], utc=True, errors="coerce")
    old = old.dropna(subset=["timestamp"])
    new = new.dropna(subset=["timestamp"])
    if old.empty or new.empty:
        return 0

    # A merge on the key pairs every combination of matching rows, so
    # duplicated keys would inflate the count. Storage is deduped already, but
    # the incoming batch can legitimately carry two copies of the same bar.
    old = old.drop_duplicates(subset=list(_RESTATEMENT_KEY_COLUMNS), keep="last")
    new = new.drop_duplicates(subset=list(_RESTATEMENT_KEY_COLUMNS), keep="last")

    merged = new.merge(old, on=list(_RESTATEMENT_KEY_COLUMNS), how="inner",
                       suffixes=("_new", "_old"))
    if merged.empty:
        return 0

    changed = pd.Series(False, index=merged.index)
    for column in price_columns:
        a = pd.to_numeric(merged[f"{column}_new"], errors="coerce")
        b = pd.to_numeric(merged[f"{column}_old"], errors="coerce")
        # The comparison is RELATIVE, and uses the same 1e-6 tolerance the
        # verifier applies, so "restated" here means exactly what a
        # verification mismatch means there. An absolute floor would be wrong:
        # for a sub-dollar stock (ACH at 0.21) a 1e-9 absolute difference is
        # already a 5e-9 relative one, but for a VND stock (VCB at 54,200)
        # the same absolute difference is 2e-14 relative - float noise, not a
        # revision.
        diff = (a - b).abs()
        scale = b.abs().clip(lower=1e-9)
        changed |= (diff / scale) > 1e-6

    return int(changed.sum())
