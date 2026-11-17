"""Data ingestion and management endpoints for US stocks, fundamental, and macro."""

from fastapi import APIRouter, BackgroundTasks

from app.core.constants import GLOBAL_SYMBOLS
from app.core.logging_config import get_logger
from app.schemas.common import ok
from app.services.data_ingestion_service import get_ingestion_service

logger = get_logger(__name__)

router = APIRouter(prefix="/data", tags=["data"])


# =====================
# US Stock Data
# =====================

# Static routes must come BEFORE the /{symbol} catch-all.
@router.get("/stocks/supported")
def get_supported_stocks() -> dict:
    """Get list of supported US stocks."""
    return ok({
        "symbols": GLOBAL_SYMBOLS,
        "count": len(GLOBAL_SYMBOLS),
    })


@router.post("/stocks/ingest")
def ingest_stocks(
    background_tasks: BackgroundTasks,
    symbols: list[str] | None = None,
) -> dict:
    """Queue an ingest of US stock data for the given symbols.

    Queued as a background task for the same reason as ``/ingest/all``: the
    download loop is blocking and can run for a long time, so holding the
    HTTP connection open for it is not useful to the caller.
    """
    service = get_ingestion_service()
    targets = list(symbols) if symbols else None

    def _job() -> None:
        try:
            service.ingest_us_stocks(targets)
        except Exception as exc:  # noqa: BLE001 - a background job must not kill the server
            logger.exception("Stock ingestion failed: %s", exc)

    background_tasks.add_task(_job)
    return ok({"queued": True, "symbols": targets or "all"})


@router.get("/stocks/{symbol}/latest")
def get_stock_latest(symbol: str) -> dict:
    """Get latest US stock data."""
    service = get_ingestion_service()
    frame = service.stock_provider.get_historical_data(
        symbol.upper(),
        start=None,
        end=None,
        interval="1d"
    )
    return ok({
        "symbol": symbol.upper(),
        "data": frame.tail(5).to_dict("records") if not frame.empty else [],
    })


@router.get("/stocks/{symbol}")
def get_stock(symbol: str) -> dict:
    """Get US stock OHLCV data."""
    service = get_ingestion_service()
    frame = service.stock_provider.get_historical_data(symbol.upper())
    return ok({
        "symbol": symbol.upper(),
        "count": len(frame),
        "data": frame.to_dict("records") if not frame.empty else [],
    })


# =====================
# Fundamental Data
# =====================

@router.get("/fundamental/{symbol}")
def get_fundamental(symbol: str) -> dict:
    """Get fundamental data for a symbol."""
    service = get_ingestion_service()
    data = service.fundamental_provider.get_comprehensive_metrics(symbol.upper())
    return ok({
        "symbol": symbol.upper(),
        "data": data,
    })


@router.post("/fundamental/ingest")
def ingest_fundamental(
    background_tasks: BackgroundTasks,
    symbols: list[str],
) -> dict:
    """Queue an ingest of fundamental data for the given symbols."""
    service = get_ingestion_service()
    targets = list(symbols)

    def _job() -> None:
        try:
            service.ingest_fundamental(targets)
        except Exception as exc:  # noqa: BLE001 - a background job must not kill the server
            logger.exception("Fundamental ingestion failed: %s", exc)

    background_tasks.add_task(_job)
    return ok({"queued": True, "symbols": targets})


# =====================
# Macro Data
# =====================

@router.get("/macro/exchange-rate")
def get_exchange_rate() -> dict:
    """Get USD/VND exchange rate."""
    service = get_ingestion_service()
    frame = service.macro_provider.get_exchange_rate()
    return ok({
        "count": len(frame),
        "data": frame.to_dict("records") if not frame.empty else [],
    })


@router.get("/macro/gold")
def get_gold_price() -> dict:
    """Get gold prices."""
    service = get_ingestion_service()
    frame = service.macro_provider.get_gold_price()
    return ok({
        "count": len(frame),
        "data": frame.to_dict("records") if not frame.empty else [],
    })


@router.get("/macro/oil")
def get_oil_price() -> dict:
    """Get oil prices (WTI, Brent)."""
    service = get_ingestion_service()
    frame = service.macro_provider.get_oil_price()
    return ok({
        "count": len(frame),
        "data": frame.to_dict("records") if not frame.empty else [],
    })


@router.get("/macro/interest-rates")
def get_interest_rates() -> dict:
    """Get interest rates."""
    service = get_ingestion_service()
    frame = service.macro_provider.get_interest_rates()
    return ok({
        "count": len(frame),
        "data": frame.to_dict("records") if not frame.empty else [],
    })


@router.get("/macro/cpi")
def get_cpi() -> dict:
    """Get CPI data."""
    service = get_ingestion_service()
    frame = service.macro_provider.get_cpi()
    return ok({
        "count": len(frame),
        "data": frame.to_dict("records") if not frame.empty else [],
    })


@router.get("/macro/summary")
def get_macro_summary() -> dict:
    """Get all macro indicators summary."""
    service = get_ingestion_service()
    summary = service.macro_provider.get_macro_summary()
    return ok({
        "data": summary,
    })


@router.post("/macro/ingest")
def ingest_macro() -> dict:
    """Ingest all macro data."""
    service = get_ingestion_service()
    results = service.ingest_all_macro()
    return ok({
        "results": results,
    })


# =====================
# Full Pipeline
# =====================

@router.post("/ingest/all")
def ingest_all(background_tasks: BackgroundTasks) -> dict:
    """Queue a full data ingestion for all sources.

    WHY THIS IS A BACKGROUND TASK
    -----------------------------
    ``ingest_all()`` walks every supported symbol (976 at the time of
    writing) and downloads each one from the provider. Measured on this
    machine it runs for **hours**, and it is a plain blocking call.

    When it ran inside the request, the HTTP connection stayed open for the
    whole job and the client eventually timed out while the work was still
    in progress - so the caller could neither see progress nor stop it.
    Queuing it means the response returns immediately and the caller can
    check ``/admin/auto-refresh/status`` for the outcome.

    The same applies to ``/data/stocks/ingest``: it also walks a symbol
    list, so it is queued the same way.
    """
    service = get_ingestion_service()

    def _job() -> None:
        try:
            service.ingest_all()
        except Exception as exc:  # noqa: BLE001 - a background job must not kill the server
            logger.exception("Full ingestion failed: %s", exc)

    background_tasks.add_task(_job)
    return ok({"queued": True, "symbols": "all", "check": "/api/v1/admin/auto-refresh/status"})
