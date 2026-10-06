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
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pandas as pd

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.constants import GLOBAL_SYMBOLS
from app.data_sources.factory import get_data_provider
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.silver import SilverLayer
from app.lakehouse.gold import GoldLayer
from app.pipelines.orchestrator import transform_to_silver, build_gold_layer

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


class AutoRefreshService:
    """Background service that incrementally updates the lakehouse on startup + schedule."""

    def __init__(self) -> None:
        self._enabled = _env_bool("AUTO_REFRESH_ENABLED", True)
        self._on_start = _env_bool("AUTO_REFRESH_ON_START", True)
        self._interval_seconds = _env_int("AUTO_REFRESH_INTERVAL_SECONDS", 6 * 3600)
        self._batch_size = _env_int("AUTO_REFRESH_BATCH_SIZE", 20)
        self._skip_if_fresh_hours = _env_int("AUTO_REFRESH_SKIP_IF_FRESH_HOURS", 24)

        raw = os.getenv("AUTO_REFRESH_SYMBOLS", "").strip()
        if raw:
            self._symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
        else:
            self._symbols = list(GLOBAL_SYMBOLS)

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
        results: list[dict] = []
        symbols_with_new_data: list[str] = []

        for idx, sym in enumerate(target_symbols):
            if self._stop_event.is_set():
                break
            res = self._refresh_symbol(bronze, provider, sym, now)
            results.append(res)
            if res.get("new_rows", 0) > 0:
                symbols_with_new_data.append(sym)
            if (idx + 1) % self._batch_size == 0:
                logger.info(
                    "AutoRefresh progress: %d/%d symbols processed",
                    idx + 1, len(target_symbols),
                )

        # Rebuild Silver + Gold for ALL target_symbols (idempotent rebuild covers
        # symbols that previously got skipped because Bronze had no new data).
        silver_done, gold_done = 0, 0
        for sym in target_symbols:
            if self._stop_event.is_set():
                break
            try:
                transform_to_silver(sym, interval="1d")
                silver_done += 1
            except Exception as exc:
                logger.warning("AutoRefresh silver rebuild failed for %s: %s", sym, exc)
            try:
                build_gold_layer(sym)
                gold_done += 1
            except Exception as exc:
                logger.warning("AutoRefresh gold rebuild failed for %s: %s", sym, exc)

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
            existing = bronze.read(symbol)
        except Exception as exc:
            logger.warning("AutoRefresh: bronze read failed for %s: %s", symbol, exc)
            existing = pd.DataFrame()

        is_new_symbol = existing.empty
        if is_new_symbol:
            # Full backfill
            start = now - timedelta(days=settings.default_lookback_days)
            skip_reason = None
        else:
            latest_ts = pd.to_datetime(existing["timestamp"], utc=True).max()
            latest_date = latest_ts.date() if hasattr(latest_ts, "date") else latest_ts
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
            # Fetch only from next day after latest
            start = latest_ts.to_pydatetime().replace(tzinfo=None) + timedelta(days=1)
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
            new_rows = int(meta.get("records_written", 0))
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
