"""Stock market data endpoints."""

import threading
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_market_service
from app.core.config import settings
from app.core.constants import GLOBAL_SYMBOLS, currency_for_symbol
from app.core.logging_config import get_logger
from app.lakehouse.storage_factory import get_storage_backend
from app.schemas.common import ok
from app.services.market_service import MarketService

logger = get_logger(__name__)
router = APIRouter(prefix="/stocks", tags=["stocks"])

# Cache for /stocks/symbols. Listing bronze top-level prefixes is fast on a
# healthy MinIO (~50-200ms) but balloons to multi-second when the bucket is
# being written to. The frontend polls this on every page mount, so we cache
# for 5 minutes and warm the cache in the background after the first miss.
_SYMBOLS_CACHE_TTL_SECONDS = 300.0
_symbols_lock = threading.Lock()
_symbols_cache: dict = {"value": None, "expires_at": 0.0}


def _available_symbols() -> list[str]:
    """Return symbols that have at least one parquet object in stock-bronze.
    Uses non-recursive listing to avoid timeout on large buckets."""
    try:
        storage = get_storage_backend()
        # Non-recursive: list just top-level symbol= prefix dirs (fast, no timeout)
        objects = storage.client.list_objects(
            storage._bucket("bronze"), prefix="symbol=", recursive=False
        )
        symbols: set[str] = set()
        for obj in objects:
            name = obj.object_name
            if name and name.startswith("symbol="):
                sym = name.split("/", 1)[0].split("=", 1)[1].upper()
                if sym:
                    symbols.add(sym)
        if not symbols:
            logger.warning("No symbols found in bronze, falling back to constants")
            return list(GLOBAL_SYMBOLS)
        # preserve canonical order from GLOBAL_SYMBOLS so UI lists are stable
        canonical = [s for s in GLOBAL_SYMBOLS if s in symbols]
        extras = sorted(symbols - set(canonical))
        return canonical + extras
    except Exception as exc:
        logger.warning("Could not enumerate symbols from storage: %s", exc)
        return list(GLOBAL_SYMBOLS)


@router.get("/symbols")
def get_symbols() -> dict:
    now = time.monotonic()
    with _symbols_lock:
        cached = _symbols_cache["value"]
        expires_at = _symbols_cache["expires_at"]
    if cached is not None and now < expires_at:
        return ok(cached)

    symbols = _available_symbols()
    payload = {"symbols": symbols, "count": len(symbols)}
    with _symbols_lock:
        _symbols_cache["value"] = payload
        _symbols_cache["expires_at"] = time.monotonic() + _SYMBOLS_CACHE_TTL_SECONDS
    return ok(payload)


@router.get("/{symbol}")
def get_stock(
    symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
    interval: str = Query(default="1d"),
    service: MarketService = Depends(get_market_service),
) -> dict:
    # Load the frame ONCE and derive both the history and the latest bar
    # from it.
    #
    # WHY: `get_latest` used to call `get_history` internally, so this
    # endpoint pulled the symbol's ~121 parquet partitions out of MinIO
    # twice per request and then re-sorted/re-copied the 2532 x 92 frame a
    # second time. Deriving both from one load removes that second pass.
    frame = service.get_history(symbol.upper(), start=start, end=end, interval=interval)
    latest = service.latest_from_frame(symbol.upper(), frame, interval=interval)
    return ok(
        {
            "symbol": symbol.upper(),
            "interval": interval,
            "latest": latest,
            "count": int(len(frame)),
            "rows": service.to_records(frame),
            "last_updated": latest["timestamp"],
            "data_source": latest.get("source_layer"),
            # Prices in this lakehouse are unitless: VCB trades near 53,500
            # and AAPL near 330, and both are a "close". The consumer needs to
            # know which unit this symbol's prices are in, so it can label
            # them correctly instead of assuming dong for everything.
            "currency": currency_for_symbol(symbol),
        }
    )


@router.get("/{symbol}/latest")
def get_latest(symbol: str, interval: str = "1d", service: MarketService = Depends(get_market_service)) -> dict:
    return ok(service.get_latest(symbol.upper(), interval=interval))


@router.get("/{symbol}/csv")
def download_csv(
    symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
    interval: str = "1d",
    service: MarketService = Depends(get_market_service),
) -> StreamingResponse:
    frame = service.get_history(symbol.upper(), start=start, end=end, interval=interval)
    csv_data = frame[["symbol", "timestamp", "open", "high", "low", "close", "volume"]].to_csv(index=False)
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={symbol.upper()}_{interval}.csv"},
    )
