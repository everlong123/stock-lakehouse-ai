"""Stock market data endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_market_service
from app.core.config import settings
from app.core.constants import SUPPORTED_SYMBOLS
from app.core.logging_config import get_logger
from app.lakehouse.storage_factory import get_storage_backend
from app.schemas.common import ok
from app.services.market_service import MarketService

logger = get_logger(__name__)
router = APIRouter(prefix="/stocks", tags=["stocks"])


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
            return list(SUPPORTED_SYMBOLS)
        # preserve canonical order from SUPPORTED_SYMBOLS so UI lists are stable
        canonical = [s for s in SUPPORTED_SYMBOLS if s in symbols]
        extras = sorted(symbols - set(canonical))
        return canonical + extras
    except Exception as exc:
        logger.warning("Could not enumerate symbols from storage: %s", exc)
        return list(SUPPORTED_SYMBOLS)


@router.get("/symbols")
def get_symbols() -> dict:
    symbols = _available_symbols()
    return ok({"symbols": symbols, "count": len(symbols)})


@router.get("/{symbol}")
def get_stock(
    symbol: str,
    start: datetime | None = None,
    end: datetime | None = None,
    interval: str = Query(default="1d"),
    service: MarketService = Depends(get_market_service),
) -> dict:
    frame = service.get_history(symbol.upper(), start=start, end=end, interval=interval)
    latest = service.get_latest(symbol.upper(), interval=interval)
    return ok(
        {
            "symbol": symbol.upper(),
            "interval": interval,
            "latest": latest,
            "count": int(len(frame)),
            "rows": service.to_records(frame),
            "last_updated": latest["timestamp"],
            "data_source": latest.get("source_layer"),
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
