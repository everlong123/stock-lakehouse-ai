"""
Medallion pipeline orchestrator — single entry point for Bronze → Silver → Gold.

This module replaces the fragmented pipeline files:

    ingest_symbol        ← ingestion.py
    transform_to_silver  ← transformation.py
    validate_ohlc_frame  ← validation.py
    build_quality_report ← quality.py
    assert_quality_passed← quality.py
    build_gold_layer     ← feature_pipeline.py
    run_symbol_pipeline ← pipeline_runner.py

Usage::

    from app.pipelines import run_symbol_pipeline
    result = run_symbol_pipeline("AAPL")
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import pandas as pd

from app.core.exceptions import DataValidationError
from app.core.logging_config import get_logger
from app.data_sources.factory import get_data_provider
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1: Ingestion
# ─────────────────────────────────────────────────────────────────────────────


def ingest_symbol(
    symbol: str,
    interval: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
    source_name: str | None = None,
) -> dict:
    """Fetch OHLCV from the configured provider and append to Bronze.

    Args:
        symbol:      Ticker, e.g. "AAPL" or "VCB"
        interval:   "1d" (default) | "1h" | "15m" | "5m"
        start:      Start of date range (default: 730 days ago)
        end:        End of date range (default: now)
        source_name: Override DATA_SOURCE env var

    Returns:
        dict with keys: records_received, records_written, duplicate_count, paths, lineage
    """
    provider = get_data_provider(source_name)
    frame = provider.get_historical_data(
        symbol=symbol, start=start, end=end, interval=interval
    )
    bronze = BronzeLayer()
    metadata = bronze.append(
        frame,
        lineage={
            "provider": provider.source_name,
            "symbol": symbol.upper(),
            "interval": interval,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
    )
    logger.info(
        "Ingestion complete for %s: %s rows", symbol, metadata["records_received"]
    )
    return metadata


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2: Validation (used by Silver / tests)
# ─────────────────────────────────────────────────────────────────────────────


def validate_ohlc_frame(frame: pd.DataFrame) -> dict[str, int]:
    """Count validation issues without mutating the input.

    Returns a dict with keys: row_count, missing_count, duplicate_count,
    invalid_ohlc_count, invalid_volume_count.

    Raises DataValidationError if required columns are absent.
    """
    required = ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
    missing_cols = [col for col in required if col not in frame.columns]
    if missing_cols:
        raise DataValidationError(f"Validation missing columns: {missing_cols}")

    missing_count = int(frame[required].isna().any(axis=1).sum())
    duplicate_count = int(frame.duplicated(subset=["symbol", "timestamp"]).sum())
    invalid_ohlc_count = int(
        (
            ~(
                (frame["high"] >= frame["open"])
                & (frame["high"] >= frame["close"])
                & (frame["low"] <= frame["open"])
                & (frame["low"] <= frame["close"])
                & (frame["high"] >= frame["low"])
            )
        ).sum()
    )
    invalid_volume_count = int((frame["volume"] < 0).sum())
    return {
        "row_count": int(len(frame)),
        "missing_count": missing_count,
        "duplicate_count": duplicate_count,
        "invalid_ohlc_count": invalid_ohlc_count,
        "invalid_volume_count": invalid_volume_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3: Transform Bronze → Silver
# ─────────────────────────────────────────────────────────────────────────────


def transform_to_silver(
    symbol: str,
    interval: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
    source_name: str | None = None,
) -> dict:
    """Read Bronze for *symbol*, clean it, write Silver.

    Returns:
        {"quality": quality_report, "write": write_info}
    """
    bronze_frame = BronzeLayer().read(symbol)
    if bronze_frame.empty:
        raise DataValidationError(
            f"No Bronze data for {symbol}. Run ingest_symbol first."
        )
    silver = SilverLayer()
    silver_frame, quality = silver.transform(bronze_frame)
    write_info = silver.write(silver_frame, quality)
    logger.info("Silver transform for %s: %s", symbol, quality)
    return {"quality": quality, "write": write_info}


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4: Quality gate
# ─────────────────────────────────────────────────────────────────────────────


def build_quality_report(symbol: str) -> dict:
    """Produce a quality report from Silver data for *symbol*."""
    frame = SilverLayer().read(symbol)
    if frame.empty:
        report = {
            "symbol": symbol.upper(),
            "record_count": 0,
            "duplicate_count": 0,
            "missing_count": 0,
            "invalid_ohlc_count": 0,
            "invalid_volume_count": 0,
            "min_timestamp": None,
            "max_timestamp": None,
            "quality_status": "failed",
        }
        logger.error("Quality check failed for %s: Silver is empty.", symbol)
        return report

    counts = validate_ohlc_frame(frame)
    critical = counts["invalid_ohlc_count"] > 0 or counts["row_count"] == 0
    report = {
        "symbol": symbol.upper(),
        "record_count": counts["row_count"],
        "duplicate_count": counts["duplicate_count"],
        "missing_count": counts["missing_count"],
        "invalid_ohlc_count": counts["invalid_ohlc_count"],
        "invalid_volume_count": counts["invalid_volume_count"],
        "min_timestamp": frame["timestamp"].min().isoformat(),
        "max_timestamp": frame["timestamp"].max().isoformat(),
        "quality_status": "failed" if critical else "passed",
    }
    logger.info("Quality report for %s: %s", symbol, report)
    return report


def assert_quality_passed(report: dict) -> None:
    """Raise if quality report shows critical failure.

    Call after build_quality_report before building Gold.
    """
    if report.get("quality_status") == "failed":
        raise DataValidationError(
            f"Critical data quality failure for {report.get('symbol')}: {report}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5: Engineer Silver → Gold
# ─────────────────────────────────────────────────────────────────────────────


def build_gold_layer(symbol: str) -> dict:
    """Read Silver for *symbol*, engineer features, write Gold.

    Returns:
        {"paths": [...], "records": int}
    """
    silver_frame = SilverLayer().read(symbol)
    if silver_frame.empty:
        raise DataValidationError(
            f"No Silver data for {symbol}. Run transform_to_silver first."
        )
    gold = GoldLayer()
    gold_frame = gold.transform(silver_frame)
    write_info = gold.write(gold_frame)
    logger.info("Gold build for %s: %s rows", symbol, write_info["records"])
    return write_info


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6: Full end-to-end pipeline (idempotent)
# ─────────────────────────────────────────────────────────────────────────────


def run_symbol_pipeline(
    symbol: str,
    interval: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
    source_name: str | None = None,
    *,
    ingest: bool = True,
    skip_silver: bool = False,
    skip_gold: bool = False,
) -> dict:
    """Run the complete medallion pipeline for one symbol.

    All stages are idempotent — running twice produces the same result.

    Args:
        symbol:       Ticker, e.g. "AAPL"
        interval:     "1d" | "1h" | "15m" | "5m"
        start/end:    Date range override
        source_name:  Override DATA_SOURCE
        ingest:       Fetch from provider first (default True)
        skip_silver:  Skip Bronze→Silver (use existing Silver)
        skip_gold:    Skip Silver→Gold (stop after Silver)

    Returns:
        Dict with keys: pipeline_name, symbol, status, start_time, end_time,
        records_processed, error_count, message, silver, quality, gold.
    """
    started = datetime.now(timezone.utc)

    # Stage 1: ingest to Bronze
    if ingest:
        ingest_symbol(
            symbol, interval=interval, start=start, end=end, source_name=source_name
        )

    # Stage 3: Bronze → Silver
    if not skip_silver:
        silver_meta = transform_to_silver(
            symbol, interval=interval, start=start, end=end, source_name=source_name
        )
    else:
        silver_meta = {}

    # Stage 4: quality gate
    quality = build_quality_report(symbol)
    assert_quality_passed(quality)

    # Stage 5: Silver → Gold
    if not skip_gold:
        gold_meta = build_gold_layer(symbol)
    else:
        gold_meta = {}

    finished = datetime.now(timezone.utc)

    return {
        "pipeline_name": "stock_lakehouse_pipeline",
        "symbol": symbol.upper(),
        "source": source_name or "auto",
        "status": "success",
        "start_time": started,
        "end_time": finished,
        "records_processed": gold_meta.get("records", 0),
        "error_count": silver_meta.get("quality", {}).get("error_count", 0),
        "message": "Pipeline completed with REAL market data.",
        "silver": silver_meta,
        "quality": quality,
        "gold": gold_meta,
    }
