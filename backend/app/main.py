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
from app.api.v1.endpoints.health import warm_layer_counts
from app.core.config import settings
from app.core.exceptions import StockLakehouseError
from app.core.logging_config import get_logger, setup_logging
from app.core.seeding import set_global_seed
from app.schemas.common import fail
from app.services.auto_refresh import start_auto_refresh, stop_auto_refresh
from app.services.crawler_service import start_crawler, stop_crawler
from app.services.stream_service import start_consumer_background, stop_consumer_background

# Bronze/Silver pipeline consumer (writes Kafka messages into the lakehouse).
# Only starts when USE_KAFKA=true so local dev without Kafka still works.
_pipeline_consumer = None
# US EOD poller (yfinance 1d) — disabled by default; flip the env to enable.
_eod_poller = None
# VN REST poller (SSI iBoard, free public REST, no API key) — gives the
# Live Stream page Vietnamese tickers too. Off by default.
_vn_rest_poller = None

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
    # immediately instead of blocking the user for ~15-30s.
    try:
        warm_layer_counts()
    except Exception as exc:
        logger.warning("layer-count warmup failed: %s", exc)
    # Stream cache consumer: only starts when USE_KAFKA=true. The cache is
    # always available — publishers can also push via the REST API.
    start_consumer_background()
    # Bronze/Silver pipeline consumer — when Kafka is enabled this drains
    # the same topic into the lakehouse so /api/v1/bronze and /silver reflect
    # real-time ingestion, not just scheduled crawls.
    if settings.use_kafka:
        try:
            from app.streaming.kafka_consumer import start_consumer

            global _pipeline_consumer
            _pipeline_consumer = start_consumer(topics=["stock-ohlcv-raw"])
            logger.info("Bronze/Silver Kafka consumer started")
        except Exception as exc:
            logger.warning("Bronze/Silver consumer skipped: %s", exc)
    # US EOD poller (yfinance, free). Only starts when explicitly enabled
    # via US_EOD_POLLER_ENABLED=true. Publishes 1d bars to the same Kafka
    # topic as the real-time path so the consumer stays the single source
    # of truth. Skipped silently when Kafka is off.
    if settings.us_eod_poller_enabled and settings.use_kafka:
        try:
            from app.streaming.yfinance_eod_poller import YFinanceEodPoller

            global _eod_poller
            _eod_poller = YFinanceEodPoller(
                poll_interval_seconds=settings.us_eod_poller_interval_seconds,
            )
            _eod_poller.start()
            logger.info("YFinanceEodPoller started")
        except Exception as exc:
            logger.warning("YFinanceEodPoller skipped: %s", exc)
    # VN REST poller (SSI iBoard) — opt-in via VN_REST_POLLER_ENABLED.
    # yfinance doesn't carry HOSE/HNX/UPCoM tickers, so the lakehouse
    # needs a separate path for Vietnamese symbols.
    if settings.vn_rest_poller_enabled and settings.use_kafka:
        try:
            from app.streaming.kafka_producer import (
                DEFAULT_BOOTSTRAP_SERVERS as _KAFKA_DEFAULT,
                TOPIC_OHLCV_RAW,
            )
            from app.streaming.vn_rest_poller import VNRestPoller

            global _vn_rest_poller
            _vn_rest_poller = VNRestPoller(
                symbols=[s.strip() for s in settings.vn_ws_symbols.split(",") if s.strip()],
                kafka_topic=TOPIC_OHLCV_RAW,
                bootstrap_servers=settings.kafka_bootstrap_servers or _KAFKA_DEFAULT,
            )
            _vn_rest_poller.start()
            logger.info("VNRestPoller started")
        except Exception as exc:
            logger.warning("VNRestPoller skipped: %s", exc)
    yield
    # ── shutdown ──
    if _pipeline_consumer is not None:
        try:
            _pipeline_consumer.stop()
        except Exception:
            pass
    if _eod_poller is not None:
        try:
            _eod_poller.stop()
        except Exception:
            pass
    if _vn_rest_poller is not None:
        try:
            _vn_rest_poller.stop()
        except Exception:
            pass
    stop_auto_refresh()
    stop_crawler()
    stop_consumer_background()
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
