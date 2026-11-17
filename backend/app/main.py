"""FastAPI application entrypoint."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder as _orig_encode


def _np_safe_encode(obj, *args, **kwargs):
    """Numpy/pandas-aware encoder patch for FastAPI."""
    # pandas DataFrame/Series → list of records (orient=records style)
    if isinstance(obj, pd.DataFrame):
        df = obj.replace({pd.NA: None, np.nan: None})
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].astype(str)
        return df.to_dict(orient="records")
    if isinstance(obj, pd.Series):
        s = obj.replace({pd.NA: None, np.nan: None})
        if pd.api.types.is_datetime64_any_dtype(s):
            s = s.astype(str)
        return s.tolist()
    # pandas Timestamp scalar (the offender in market indices)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    # numpy scalar types
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (np.datetime64, np.timedelta64)):
        return str(obj)
    # objects without __dict__ that aren't basic types
    if not hasattr(obj, "__dict__") and not isinstance(
        obj, (str, int, float, bool, list, dict, tuple, type(None), bytes, bytearray)
    ):
        return str(obj)
    return _orig_encode(obj, *args, **kwargs)


import fastapi.encoders as _fe
_fe.jsonable_encoder = _np_safe_encode
import fastapi.routing as _fr
_fr.jsonable_encoder = _np_safe_encode

from app.api.v1.router import api_router
from app.api.v1.endpoints.health import restore_layer_counts, warm_layer_counts
from app.core.config import settings
from app.core.exceptions import StockLakehouseError
from app.core.heavy_worker import shutdown_pool
from app.core.logging_config import get_logger, setup_logging
from app.core.request_gate import request_finished, request_started
from app.core.seeding import set_global_seed
from app.schemas.common import fail
from app.services.auto_refresh import start_auto_refresh, stop_auto_refresh
from app.services.crawler_service import start_crawler, stop_crawler

# Load .env before anything else so all modules see the same settings
_dotenv = Path(__file__).resolve().parents[1] / ".env"
if _dotenv.exists():
    load_dotenv(_dotenv, override=True)

# Local dev override (e.g. switch service hostnames to 127.0.0.1:port
# when running on Windows without Docker). Picked up automatically —
# no need to copy the example by hand. .env.local is git-ignored.
_local = Path(__file__).resolve().parents[1] / ".env.local"
if _local.exists():
    load_dotenv(_local, override=True)

setup_logging()
set_global_seed(settings.random_seed)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ── startup ──
    # Apply database migrations (Alembic). The script auto-falls back to
    # Base.metadata.create_all + stamp head on first run if alembic.ini is
    # not yet set up.
    try:
        from scripts.init_database import create_database_if_needed, run_migrations

        create_database_if_needed()
        run_migrations()
    except Exception as exc:
        logger.warning("DB init skipped: %s", exc)
    crawler = start_crawler()
    if crawler:
        logger.info("Stock crawler started successfully")
    try:
        start_auto_refresh()
    except Exception as exc:
        logger.exception("Failed to start auto-refresh service: %s", exc)
    # Pre-warm the System Status page counts so the first request returns
    # immediately instead of blocking the user for ~15-30s. Skippable via
    # WARM_LAYER_COUNTS_ON_START=false — the warmup walks ~300k objects in
    # MinIO, which costs 20-30s of CPU on every boot.
    if settings.warm_layer_counts_on_start:
        try:
            warm_layer_counts()
        except Exception as exc:
            logger.warning("layer-count warmup failed: %s", exc)
    else:
        logger.info("layer-count warmup skipped (WARM_LAYER_COUNTS_ON_START=false)")
    # Restore the counts a previous run persisted. Recomputing them walks
    # ~340k MinIO object keys, and while the auto-refresh pass holds the GIL
    # that job can take minutes - so after a restart the System Status page
    # would show zeros for a long time. The persisted numbers are a
    # slow-moving statistic, so serving them immediately is accurate enough,
    # and the background job refines them.
    try:
        restore_layer_counts()
    except Exception as exc:
        logger.warning("layer-count restore failed: %s", exc)
    yield
    # ── shutdown ──
    stop_auto_refresh()
    stop_crawler()
    # Tear down the CPU-bound job process pool. The children are daemonic
    # workers, so leaving them alive would keep the interpreter from exiting
    # cleanly on shutdown.
    shutdown_pool()
    logger.info("Background services stopped")


app = FastAPI(
    title=settings.app_name,
    description=(
        "Nền tảng Data Lakehouse phân tích và dự báo chứng khoán phục vụ nghiên cứu học thuật. "
        "Kết quả không phải khuyến nghị đầu tư và không cam kết lợi nhuận."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compress the JSON responses.
#
# WHY: the price-history payload for one symbol is ~567 KB of JSON (2532
# daily bars x 10 fields). It is highly repetitive numeric text, so gzip
# shrinks it to roughly 60 KB - a ~10x reduction in what the browser has to
# pull over the wire for every stock the user clicks through.
#
# The minimum size is 1 KB so small responses (health checks, symbol lists)
# are not worth compressing.
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)


@app.middleware("http")
async def track_inflight_requests(request: Request, call_next):
    """Tell the background lakehouse work that a user is waiting.

    WHY: the auto-refresh pass rebuilds Silver+Gold for ~973 symbols in the
    same process, and each rebuild rewrites ~242 monthly partitions in MinIO.
    A read that lands in that window waits behind them - the same symbol read
    took 0.4s on an idle box and 90s during a rebuild, which is what pushed
    the agent past the frontend's 90s timeout.

    While this counter is above zero the background pass waits. The refresh
    therefore takes longer to finish, but every interactive request becomes
    fast and predictable - which is the right trade-off for a UI-driven
    research tool.
    """
    request_started()
    try:
        return await call_next(request)
    finally:
        request_finished()

app.include_router(api_router, prefix=settings.api_prefix)


@app.exception_handler(StockLakehouseError)
async def domain_exception_handler(_request: Request, exc: StockLakehouseError) -> JSONResponse:
    logger.warning("Domain error: %s", exc.message)
    return JSONResponse(status_code=exc.status_code, content=fail(exc.message))


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content=fail("Internal server error."))


@app.get("/")
def root() -> dict:
    return {
        "success": True,
        "data": {
            "name": settings.app_name,
            "docs": "/docs",
            "api": settings.api_prefix,
        },
        "message": "Research prototype. Not investment advice.",
    }
