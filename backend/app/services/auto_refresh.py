"""
Auto-refresh service — incremental Bronze → Silver → Gold refresh on startup + periodic.

Design:
- On FastAPI startup, run a one-shot incremental refresh so data reaches "today".
- Then run periodic refresh every `auto_refresh_interval_seconds` (default 6h).
- Each symbol is processed independently:
  * If Bronze has no data, do a full history fetch (default_lookback_days).
  * Else, fetch only from (max_timestamp.date + 1 day) to now.
- Bronze append is idempotent (drops duplicates on symbol+timestamp).
- After Bronze append, if new rows were added, rebuild Silver and Gold.
- Configurable via env:
    AUTO_REFRESH_ON_START=1            (default 1)
    AUTO_REFRESH_ENABLED=1             (default 1)
    AUTO_REFRESH_INTERVAL_SECONDS=21600 (default 6h)
    AUTO_REFRESH_SYMBOLS=              (default = SUPPORTED_SYMBOLS; comma-sep; empty=all)
    AUTO_REFRESH_BATCH_SIZE=20         (default 20)
    AUTO_REFRESH_SKIP_IF_FRESH_HOURS=24 (skip if data <= N hours old)
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pandas as pd

from app.core.config import settings
from app.core.heavy_worker import run_in_process
from app.core.logging_config import get_logger
from app.core.constants import CRYPTO_SYMBOLS, GLOBAL_SYMBOLS, VN_SYMBOLS
from app.core.request_gate import wait_while_user_active
from app.data_sources.factory import get_data_provider
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.silver import SilverLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.session import session_date
from app.pipelines.orchestrator import transform_to_silver, build_gold_layer
from app.pipelines.worker import rebuild_gold_job, rebuild_silver_job

# The market read path (`MarketService._load_symbol_frame`) memoises every
# symbol frame with `lru_cache` and no TTL. Without an explicit drop here the
# UI keeps serving whatever was read at first request, so freshly ingested
# Bronze/Silver/Gold rows never surface until the process restarts. The
# manual `run_pipeline` path already calls this in the orchestrator; the
# auto-refresh loop must do the same per symbol, right after it writes.
from app.services.market_service import clear_symbol_cache, invalidate_symbol_cache

logger = get_logger(__name__)


def _env_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


# Free RAM (in MB) below which the refresh must NOT start a rebuild.
#
# WHY: this host had no Windows pagefile, so the commit limit equalled
# physical RAM (31.8 GB). Once the commit charge got close to that limit,
# Windows killed whatever asked for memory next - and the next thing to
# ask was the rebuild worker we were about to spawn. The rebuild then died
# halfway, leaving Silver and Gold half-written.
#
# The evidence is in the Windows System log for 2026-11-03:
#
#   Event 2004 x7  "low virtual memory condition"
#     vmmemWSL   consumed 12.9 GB
#     python.exe consumed  1.67 GB
#   Event 1000    wslservice.exe / wslrelay.exe faulted
#
# 6 GB is roughly "the host is running out of room": enough for Windows,
# Cursor, the browser and the pool to keep working, while a rebuild needs
# about 700 MB per worker.
MEMORY_HEADROOM_MB = int(os.getenv("AUTO_REFRESH_MEMORY_HEADROOM_MB", "6144"))


def _memory_headroom_ok() -> bool:
    """True when there is enough free RAM to safely start a rebuild."""
    try:
        from app.core.heavy_worker import _available_memory_mb

        available = _available_memory_mb()
    except Exception:  # noqa: BLE001 - never block the refresh on a probe error
        return True
    if available <= 0:
        # Could not read the value; do not block the refresh on a guess.
        return True
    return available >= MEMORY_HEADROOM_MB


class AutoRefreshService:
    """Background service that incrementally updates the lakehouse on startup + schedule."""

    def __init__(self) -> None:
        self._enabled = _env_bool("AUTO_REFRESH_ENABLED", settings.auto_refresh_enabled)
        self._on_start = _env_bool("AUTO_REFRESH_ON_START", True)
        self._interval_seconds = _env_int("AUTO_REFRESH_INTERVAL_SECONDS", 6 * 3600)
        self._batch_size = _env_int("AUTO_REFRESH_BATCH_SIZE", 20)
        self._skip_if_fresh_hours = _env_int("AUTO_REFRESH_SKIP_IF_FRESH_HOURS", 24)

        raw = os.getenv("AUTO_REFRESH_SYMBOLS", "").strip()
        if raw:
            self._symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
        else:
            # VN_SYMBOLS are included on purpose. GLOBAL_SYMBOLS only holds the
            # Yahoo-listed universe, so without this the ~80 HOSE/HNX/UPCoM
            # tickers (VNM, HPG, FPT, ...) were never refreshed and froze on
            # whatever day they were last ingested. They are served by the SSI
            # iBoard provider, which is reachable through the same failover
            # chain (see app/data_sources/multi_source.py).
            #
            # The dict dedupes: FRT, NET, DBC and HDB appear in both lists and
            # the lakehouse keys rows by the bare ticker, so they must only be
            # visited once per pass.
            merged = {s: None for s in GLOBAL_SYMBOLS}
            for s in VN_SYMBOLS:
                merged.setdefault(s, None)
            for s in CRYPTO_SYMBOLS:
                merged.setdefault(s, None)
            self._symbols = list(merged)

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_run_at: datetime | None = None
        self._last_summary: dict = {}

    # ── public API ─────────────────────────────────────────────────────────
    def start(self) -> None:
        """Start the service. Run a one-shot refresh if AUTO_REFRESH_ON_START, then loop."""
        if not self._enabled:
            logger.info("AutoRefreshService disabled via AUTO_REFRESH_ENABLED=0")
            return
        if self._thread and self._thread.is_alive():
            logger.warning("AutoRefreshService already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="AutoRefresh"
        )
        self._thread.start()
        logger.info(
            "AutoRefreshService started: on_start=%s interval=%ss symbols=%d batch_size=%d",
            self._on_start, self._interval_seconds, len(self._symbols), self._batch_size,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("AutoRefreshService stopped")

    @property
    def last_run_at(self) -> datetime | None:
        return self._last_run_at

    @property
    def last_summary(self) -> dict:
        return dict(self._last_summary)

    # ── internals ──────────────────────────────────────────────────────────
    def _run(self) -> None:
        # On-start one-shot
        if self._on_start:
            try:
                self.run_once()
            except Exception as exc:
                logger.exception("AutoRefreshService on-start run failed: %s", exc)

        # Periodic loop
        while not self._stop_event.is_set():
            # Sleep in small slices so stop() is responsive
            slept = 0.0
            while slept < self._interval_seconds and not self._stop_event.is_set():
                time.sleep(min(5.0, self._interval_seconds - slept))
                slept += 5.0
            if self._stop_event.is_set():
                break
            try:
                self.run_once()
            except Exception as exc:
                logger.exception("AutoRefreshService periodic run failed: %s", exc)

    def run_once(self, symbols: Iterable[str] | None = None) -> dict:
        """Run one full incremental refresh pass. Returns summary dict."""
        started = datetime.now(timezone.utc)
        provider = get_data_provider()
        bronze = BronzeLayer()

        target_symbols = list(symbols) if symbols is not None else list(self._symbols)
        if not target_symbols:
            logger.warning("AutoRefresh: no symbols configured, skipping")
            return {"skipped": True, "reason": "no_symbols"}

        now = datetime.now(timezone.utc)
        symbols_with_new_data: list[str] = []

        # Fetch symbols concurrently. Each fetch is I/O-bound (HTTP + MinIO),
        # so threads give a large speedup over the sequential loop that made a
        # 958-symbol pass take tens of minutes. `_refresh_symbol` is safe to
        # call from several threads: it only reads its own watermark, appends
        # to the symbol's own partition prefix, and returns a plain dict.
        worker_count = max(1, _env_int("AUTO_REFRESH_WORKERS", 8))
        results: list[dict] = [{} for _ in target_symbols]
        completed = 0

        # Silver/Gold bookkeeping. The rebuild happens INLINE for each symbol as
        # soon as its fetch finishes, not in a separate loop after all ~958
        # fetches. Why: this backend runs under WSL2, and the distro is torn
        # down and restarted by WSL itself every few minutes (see
        # InitTerminateInstanceInternal in the WSL journal). A pass only ever
        # reaches ~220/958 symbols before the process is killed, so a rebuild
        # that ran after the fetch loop NEVER executed — Bronze advanced daily
        # while Silver/Gold stayed frozen at the last clean pass. Rebuilding per
        # symbol means every pass makes forward progress that survives a kill.
        from app.lakehouse.gold import GoldLayer
        _gold = GoldLayer()
        silver_done, gold_done = 0, 0
        _counts_lock = threading.Lock()

        def _rebuild_layers(sym: str, res: dict) -> None:
            """Bring Silver+Gold in line with Bronze for one symbol, inline."""
            nonlocal silver_done, gold_done
            if self._stop_event.is_set() or res.get("error"):
                return
            # A Silver+Gold rebuild rewrites ~121 monthly partitions per layer.
            # Doing that while the user is waiting on the API starves the read
            # path: the same symbol read took 0.4s on an idle box and 90s
            # during a rebuild. The background work is not valuable while
            # somebody is waiting on the UI, so it waits.
            wait_while_user_active(stop_event=self._stop_event)
            if self._stop_event.is_set():
                return
            # ``new_rows`` counts rows that are genuinely NEW to Bronze
            # (post-dedupe growth of the stored partitions), not the size of
            # the incoming batch. The fetch window overlaps the stored data
            # by 5 days on purpose, so most batches are entirely duplicates.
            # Counting the batch made every symbol look "changed" and forced a
            # full Silver + Gold rebuild for all ~950 symbols on every pass.
            needs_rebuild = res.get("new_rows", 0) > 0
            if not needs_rebuild:
                # Bronze unchanged for this symbol, but a previous pass may have
                # been killed between the Bronze write and the Gold write, which
                # leaves Gold lagging Bronze forever unless we repair it here.
                try:
                    bronze_ts = bronze.latest_timestamp(sym)
                    gold_ts = _gold.latest_timestamp(sym) if bronze_ts is not None else None
                    # Compare by trading day, not by raw timestamp: Bronze can
                    # hold an after-hours bar at 20:00 UTC for a session that
                    # Gold stamps at 13:30, and comparing those raw values
                    # would rebuild the symbol on every pass forever.
                    bronze_day = session_date(bronze_ts)
                    gold_day = session_date(gold_ts)
                    needs_rebuild = bronze_day is not None and (
                        gold_day is None or gold_day < bronze_day
                    )
                    if needs_rebuild:
                        logger.info(
                            "AutoRefresh: %s Gold watermark (%s) lags Bronze (%s), rebuilding",
                            sym,
                            gold_day if gold_day else "MISSING",
                            bronze_day,
                        )
                except Exception as exc:
                    logger.warning("AutoRefresh: watermark compare failed for %s: %s", sym, exc)
                    return
            if not needs_rebuild:
                return
            # Do not start a rebuild if the machine is already starved of RAM.
            #
            # WHY: this host has no pagefile (until recently), so the commit
            # limit equals physical RAM. When the commit charge approaches
            # that limit, Windows kills whatever asks for memory next -
            # which is exactly the worker process we are about to spawn. The
            # rebuild would then die halfway through and leave Silver and
            # Gold half-written.
            #
            # The Windows event log recorded this on 2026-11-03: Event 2004
            # "low virtual memory condition" fired 7 times in an hour while
            # vmmemWSL held 12.9 GB, and the job workers were killed
            # mid-rebuild.
            #
            # Pausing is the right call: the refresh can resume later, but a
            # half-written Silver layer cannot be un-corrupted.
            if not _memory_headroom_ok():
                logger.warning(
                    "AutoRefresh: skipping rebuild for %s - not enough free RAM "
                    "(the rebuild workers would be killed).",
                    sym,
                )
                return
            # The rebuild itself runs in a CHILD PROCESS.
            #
            # WHY: rebuilding Silver+Gold for one symbol reads the symbol's
            # whole history from MinIO, canonicalises it, computes ~90
            # indicator columns and writes ~242 monthly partitions. That is
            # pure pandas work, so in the API process it competes for the GIL
            # with every interactive request. Measured: a walk-forward
            # validation took 2.2s on an idle box, 13.3s while the refresh
            # ran, and 96s under real server load - which blew the agent's
            # 75s deadline and showed the user "Yêu cầu mất quá lâu".
            #
            # A child process has its own GIL, so the refresh keeps its
            # throughput AND the request path keeps its speed.
            try:
                run_in_process(rebuild_silver_job, sym, "1d", pool_name="background")
                with _counts_lock:
                    silver_done += 1
            except Exception as exc:
                logger.warning("AutoRefresh silver rebuild failed for %s: %s", sym, exc)
            try:
                run_in_process(rebuild_gold_job, sym, pool_name="background")
                with _counts_lock:
                    gold_done += 1
            except Exception as exc:
                logger.warning("AutoRefresh gold rebuild failed for %s: %s", sym, exc)
            # Drop the memoised frame for THIS symbol so the UI immediately
            # serves the rows we just wrote instead of a pre-ingest snapshot.
            # Done per symbol (not once at the end) so pages opened mid-pass
            # show partial progress rather than nothing until the pass ends.
            #
            # Only this symbol's entry is dropped. `clear_symbol_cache()` would
            # wipe the whole cache, and since the pass rebuilds ~950 symbols in
            # a row, every page the user had open would have to re-download
            # its symbol's ~120 parquet partitions from MinIO on the next
            # request — turning a 1s page load into a multi-minute hang that
            # the frontend's 90s timeout cut off.
            invalidate_symbol_cache(sym)

        # Rebuilds run on their own pool so a slow Silver/Gold write for one
        # symbol never stalls the HTTP fetch of the next ~950.
        rebuild_count = max(1, _env_int("AUTO_REFRESH_REBUILD_WORKERS", 4))
        rebuild_futures = []
        with ThreadPoolExecutor(max_workers=worker_count) as pool, ThreadPoolExecutor(
            max_workers=rebuild_count,
        ) as rebuild_pool:
            # The fetch loop also waits while the user is waiting. Fetching is
            # mostly I/O (the provider HTTP call) but each symbol also reads
            # its Bronze watermark and appends a partition, and 8 workers
            # doing that at once competes with the read path for the MinIO
            # connection pool. Pausing here keeps the interactive path fast
            # without giving up on the refresh.
            def _fetch_with_gate(symbol: str) -> dict:
                wait_while_user_active(stop_event=self._stop_event)
                if self._stop_event.is_set():
                    return {
                        "symbol": symbol,
                        "skipped": True,
                        "reason": "stopped",
                        "new_rows": 0,
                        "is_new_symbol": False,
                    }
                return self._refresh_symbol(bronze, provider, symbol, now)

            futures = {
                pool.submit(_fetch_with_gate, sym): idx
                for idx, sym in enumerate(target_symbols)
            }
            for future in as_completed(futures):
                idx = futures[future]
                sym = target_symbols[idx]
                try:
                    results[idx] = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("AutoRefresh: unexpected failure for %s: %s", sym, exc)
                    results[idx] = {
                        "symbol": sym, "error": str(exc),
                        "new_rows": 0, "is_new_symbol": False,
                    }
                # Queue the rebuild immediately so a WSL-initiated kill can only
                # lose the symbols in flight, never the whole backlog.
                rebuild_futures.append(
                    rebuild_pool.submit(_rebuild_layers, sym, results[idx])
                )
                completed += 1
                if completed % self._batch_size == 0:
                    logger.info(
                        "AutoRefresh progress: %d/%d symbols processed (silver=%d gold=%d)",
                        completed, len(target_symbols), silver_done, gold_done,
                    )

            for rf in as_completed(rebuild_futures):
                try:
                    rf.result()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("AutoRefresh: rebuild task failed: %s", exc)

        for res in results:
            if res.get("new_rows", 0) > 0:
                symbols_with_new_data.append(res["symbol"])

        logger.info(
            "AutoRefresh: %d/%d symbols had Silver/Gold rebuilt (silver=%d gold=%d)",
            max(silver_done, gold_done), len(target_symbols), silver_done, gold_done,
        )

        finished = datetime.now(timezone.utc)
        summary = {
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_seconds": (finished - started).total_seconds(),
            "symbols_total": len(target_symbols),
            "symbols_with_new_data": len(symbols_with_new_data),
            "new_symbols_added": sum(1 for r in results if r.get("new_rows", 0) > 0 and r.get("is_new_symbol")),
            "total_new_rows": sum(r.get("new_rows", 0) for r in results),
            "silver_rebuilt": silver_done,
            "gold_rebuilt": gold_done,
            "errors": [r for r in results if r.get("error")],
        }
        self._last_run_at = finished
        self._last_summary = summary
        logger.info("AutoRefresh pass complete: %s", summary)
        return summary

    def _refresh_symbol(
        self,
        bronze: BronzeLayer,
        provider,
        symbol: str,
        now: datetime,
    ) -> dict:
        """Incrementally fetch one symbol. Returns dict with details."""
        try:
            # Only the watermark is needed here. `bronze.read()` would download
            # every month partition for the symbol (~120 objects for a 10-year
            # daily ticker) once per pass, which is what made the refresh crawl.
            # `latest_timestamp()` lists keys and pulls just the newest partition.
            latest_ts = bronze.latest_timestamp(symbol)
        except Exception as exc:
            logger.warning("AutoRefresh: bronze watermark read failed for %s: %s", symbol, exc)
            latest_ts = None

        is_new_symbol = latest_ts is None
        if is_new_symbol:
            # Full backfill
            start = now - timedelta(days=settings.default_lookback_days)
            skip_reason = None
        else:
            # Skip if already fresh
            now_naive = now.replace(tzinfo=None)
            age_hours = (now_naive - latest_ts.to_pydatetime().replace(tzinfo=None)).total_seconds() / 3600.0
            if age_hours <= self._skip_if_fresh_hours:
                return {
                    "symbol": symbol,
                    "skipped": True,
                    "reason": f"data is {age_hours:.1f}h old (<= {self._skip_if_fresh_hours}h)",
                    "new_rows": 0,
                    "is_new_symbol": False,
                }
            # Re-fetch from a few days BEFORE the newest stored bar.
            #
            # WHY the overlap: the stored bar's timestamp is the exchange's
            # session OPEN expressed in UTC - 13:30 UTC in EDT, 14:30 UTC in
            # EST, 02:00 UTC for HOSE. A provider stamps the bar for a given
            # trading day at that same instant, so asking for "the day after
            # the last bar" is ambiguous: if the last bar is the settled
            # 20:00 copy, the next day's open-stamped bar is EARLIER than the
            # requested boundary and never comes back. The day is then lost
            # permanently - the symbol advances and the hole stays.
            #
            # The measured symptom was 358 symbols missing 2026-10-21 while
            # 489 of their peers had it, and a lineage sidecar showing
            # `start=2026-10-24T13:30` for a symbol whose newest bar was
            # 2026-10-22 - the fetch had walked straight over two trading
            # days. A 5-day overlap is cheap (a handful of extra rows that
            # Bronze's idempotent dedupe discards) and it makes the refresh
            # self-healing: a previously skipped day is picked up on the next
            # pass, because the request window no longer starts after it.
            overlap_days = _env_int("AUTO_REFRESH_OVERLAP_DAYS", 5)
            start = latest_ts.to_pydatetime() - timedelta(days=overlap_days)
            skip_reason = None

        # If start is in the future, nothing to do
        start_for_compare = start if getattr(start, "tzinfo", None) else start.replace(tzinfo=timezone.utc) if hasattr(start, "replace") else start
        if start_for_compare >= now:
            return {
                "symbol": symbol,
                "skipped": True,
                "reason": "no missing days",
                "new_rows": 0,
                "is_new_symbol": is_new_symbol,
            }

        # The providers now read a naive boundary as UTC, so the bounds are
        # passed through unchanged. Keeping them aware avoids any ambiguity
        # about which calendar day the request covers.
        start_naive = start.replace(tzinfo=None) if hasattr(start, "replace") else start
        end_naive = now.replace(tzinfo=None)

        try:
            frame = provider.get_historical_data(
                symbol=symbol, start=start_naive, end=end_naive, interval="1d"
            )
        except Exception as exc:
            logger.warning("AutoRefresh: provider fetch failed for %s: %s", symbol, exc)
            return {"symbol": symbol, "error": str(exc), "new_rows": 0, "is_new_symbol": is_new_symbol}

        if frame is None or frame.empty:
            return {
                "symbol": symbol,
                "skipped": True,
                "reason": "provider returned empty frame",
                "new_rows": 0,
                "is_new_symbol": is_new_symbol,
            }

        try:
            meta = bronze.append(
                frame,
                lineage={
                    "source": "auto_refresh",
                    "provider": provider.source_name,
                    "symbol": symbol,
                    "interval": "1d",
                    "start": start_naive.isoformat(),
                    "end": end_naive.isoformat(),
                },
            )
            new_rows = int(meta.get("new_records", 0))
        except Exception as exc:
            logger.warning("AutoRefresh: bronze append failed for %s: %s", symbol, exc)
            return {"symbol": symbol, "error": str(exc), "new_rows": 0, "is_new_symbol": is_new_symbol}

        return {
            "symbol": symbol,
            "new_rows": new_rows,
            "is_new_symbol": is_new_symbol,
            "from": start_naive.isoformat() if hasattr(start_naive, "isoformat") else str(start_naive),
            "to": end_naive.isoformat(),
        }


# ── Module-level singleton ──────────────────────────────────────────────────
_service: AutoRefreshService | None = None


def get_service() -> AutoRefreshService:
    global _service
    if _service is None:
        _service = AutoRefreshService()
    return _service


def start_auto_refresh() -> AutoRefreshService | None:
    """Start the global auto-refresh service."""
    svc = get_service()
    svc.start()
    return svc


def stop_auto_refresh() -> None:
    global _service
    if _service:
        _service.stop()
        _service = None
