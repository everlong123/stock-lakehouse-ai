"""
Dagster Definitions - Stock Lakehouse Pipeline Orchestration
===========================================================

This module defines Dagster assets and jobs for the medallion pipeline.
It wraps the existing pipeline_runner logic into observable, schedulable units.

Key concepts:
- Ops: Individual atomic steps (ingest, transform, validate, gold)
- Job: A collection of ops forming a pipeline
- Schedule: Automated triggers (e.g. daily at market close)
- Asset: Declarative data outputs with lineage tracking

Why Dagster (vs Airflow used in the reference project):
1. Native Python-first design - no YAML DAG authoring
2. Asset-based model - tracks data lineage automatically
3. Built-in data quality assertions as code
4. Better testing story with dagster unit test utilities
5. Modern UI with asset graphs and run history

References:
- Dagster docs: https://docs.dagster.io/
- Dagster GitHub: https://github.com/dagster-io/dagster
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any

# ── Dagster imports ──────────────────────────────────────────────────────────
from dagster import (
    AssetDep,
    AssetIn,
    AssetKey,
    Config,
    DagsterRunStatus,
    Failure,
    MaterializeResult,
    OpExecutionContext,
    Output,
    RunConfig,
    Schedule,
    schedule,
    AssetSelection,
    define_asset_job,
    fs_io_manager,
    graph_asset,
    io_manager,
    job,
    op,
    repository,
    resource,
)
from dagster._core.definitions.assets import AssetsDefinition
from dagster._core.definitions.declarative_automation.automation_condition import (
    AutomationCondition,
)
from dagster._core.definitions.resource_output_context import ResourceOutputContext

# ── Add backend to path so we can import app modules ──────────────────────────
BACKEND_PATH = os.environ.get("DAGSTER_BACKEND_PATH", "/opt/dagster/app/backend")
if BACKEND_PATH not in sys.path:
    sys.path.insert(0, BACKEND_PATH)

# ── Import pipeline functions from existing codebase ───────────────────────────
from app.pipelines.ingestion import ingest_symbol
from app.pipelines.quality import assert_quality_passed, build_quality_report
from app.pipelines.transformation import transform_to_silver
from app.pipelines.feature_pipeline import build_gold_layer


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

class LakehouseConfig(Config):
    """Shared config for all pipeline ops."""

    symbols: list[str] = ["AAPL", "MSFT", "GOOGL"]
    interval: str = "1d"
    source_name: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# IO MANAGER  (how Dagster persists data between ops)
# ═══════════════════════════════════════════════════════════════════════════════

class PipelineIOManager(io_manager):
    """
    Custom IO manager that stores op outputs as JSON metadata in the run DB.

    In production you would persist DataFrames to MinIO/Parquet here.
    This lightweight version stores metadata for observability.
    """

    def __init__(self):
        self._cache: dict[str, Any] = {}

    def handle_output(self, context: ResourceOutputContext, obj: Any) -> None:
        """Called after an op finishes; obj is the return value."""
        step_key = context.step_key
        self._cache[step_key] = obj
        # Log to context for UI visibility
        context.log.info(f"[{step_key}] Output cached: {type(obj).__name__}")

    def load_input(self, context: ResourceOutputContext) -> Any:
        """Called before downstream op starts; fetch from upstream output."""
        upstream_step = context.upstream_step_key
        return self._cache.get(upstream_step)

    def get_cache(self) -> dict[str, Any]:
        return self._cache.copy()


pipeline_io_manager = PipelineIOManager()


# ═══════════════════════════════════════════════════════════════════════════════
# RESOURCE  (shared external clients)
# ═══════════════════════════════════════════════════════════════════════════════

class LakehouseResource(resource):
    """
    Resource holding shared lakehouse clients (MinIO, Spark, etc).

    In this lightweight implementation we initialize Spark on first use.
    Swap spark_session.py logic here for production use.
    """

    def __init__(self):
        self._spark = None
        self._minio_client = None

    def initialize(self) -> None:
        """Called by Dagster before the run starts."""
        import logging
        logging.getLogger("py4j").setLevel(logging.WARNING)

    def get_spark(self):
        if self._spark is None:
            from app.lakehouse.spark_session import get_spark_session
            self._spark = get_spark_session()
        return self._spark

    def cleanup(self) -> None:
        """Called by Dagster after the run finishes."""
        if self._spark:
            self._spark.stop()
            self._spark = None


lakehouse_resource = LakehouseResource()


# ═══════════════════════════════════════════════════════════════════════════════
# OPS  (atomic pipeline steps)
# ═══════════════════════════════════════════════════════════════════════════════

@op(
    name="ingest_bronze",
    description="Fetch OHLCV data from provider and write to Bronze layer.",
    required_resource_keys={"lakehouse"},
    tags={"layer": "bronze", "medallion": "bronze"},
)
def ingest_bronze(context: OpExecutionContext, config: LakehouseConfig) -> dict:
    """
    Op 1: Ingest raw market data into Bronze layer.

    This op fetches data from yfinance/web scraping/etc and stores it
    in its raw form with lineage metadata attached.

    Why Bronze?
    - Stores data as-is from source (no cleaning)
    - Preserves all fields including those later deemed unreliable
    - Enables reprocessing if source format changes
    """
    results = {}
    for symbol in config.symbols:
        context.log.info(f"[ingest_bronze] Fetching {symbol} from {config.source_name or 'default provider'}")
        meta = ingest_symbol(
            symbol=symbol,
            interval=config.interval,
            source_name=config.source_name,
        )
        results[symbol] = meta
        context.log.info(f"[ingest_bronze] {symbol}: {meta.get('records_received', 0)} rows written")
    return results


@op(
    name="transform_silver",
    description="Clean and standardize Bronze data, write to Silver layer.",
    required_resource_keys={"lakehouse"},
    tags={"layer": "silver", "medallion": "silver"},
)
def transform_silver(context: OpExecutionContext, config: LakehouseConfig) -> dict:
    """
    Op 2: Bronze → Silver transformation.

    This op reads raw Bronze data, applies cleaning rules:
    - Remove duplicates
    - Handle missing values
    - Standardize column names/dtypes
    - Validate OHLC relationships (High >= Low, etc)

    Why Silver?
    - Clean, validated dataset ready for analysis
    - Queryable by business users without data engineering knowledge
    - Single source of truth for downstream models
    """
    results = {}
    for symbol in config.symbols:
        context.log.info(f"[transform_silver] Processing {symbol}")
        result = transform_to_silver(symbol)
        quality = result.get("quality", {})
        context.log.info(
            f"[transform_silver] {symbol}: {quality.get('row_count', 0)} rows, "
            f"errors={quality.get('error_count', 0)}"
        )
        results[symbol] = result
    return results


@op(
    name="validate_quality",
    description="Run quality checks on Silver data before Gold build.",
    required_resource_keys={"lakehouse"},
    tags={"layer": "quality", "medallion": "quality"},
)
def validate_quality(context: OpExecutionContext, config: LakehouseConfig) -> dict:
    """
    Op 3: Quality gate - validate Silver before Gold.

    Runs checks defined in validation.py:
    - Completeness (no nulls in critical fields)
    - Uniqueness (no duplicate timestamp+symbol)
    - Validity (OHLC relationships, positive volumes)
    - Freshness (data within expected time range)

    If checks fail, the op raises a Dagster Failure and the
    pipeline halts - no Gold build on bad data.
    """
    reports = {}
    for symbol in config.symbols:
        context.log.info(f"[validate_quality] Checking {symbol}")
        report = build_quality_report(symbol)
        status = report.get("quality_status", "unknown")
        context.log.info(f"[validate_quality] {symbol}: status={status}, records={report.get('record_count')}")

        if status == "failed":
            context.log.error(f"[validate_quality] FAILED for {symbol}: {report}")
            raise Failure(
                description=f"Quality check failed for {symbol}",
                metadata={
                    "symbol": symbol,
                    "report": str(report),
                },
            )
        reports[symbol] = report
    return reports


@op(
    name="build_gold",
    description="Feature engineering and ML-ready dataset in Gold layer.",
    required_resource_keys={"lakehouse"},
    tags={"layer": "gold", "medallion": "gold"},
)
def build_gold(context: OpExecutionContext, config: LakehouseConfig) -> dict:
    """
    Op 4: Silver → Gold feature engineering.

    This op reads clean Silver data and creates:
    - Technical indicators (SMA, EMA, RSI, MACD, Bollinger)
    - Target variables for ML (next-day return, direction)
    - Aggregated features (rolling stats, lag features)
    - Train/test splits

    Why Gold?
    - Business-ready, domain-specific features
    - Optimized for ML workloads (no redundant computation)
    - Partitioned for fast reads during training/inference
    """
    results = {}
    for symbol in config.symbols:
        context.log.info(f"[build_gold] Engineering features for {symbol}")
        result = build_gold_layer(symbol)
        results[symbol] = result
        context.log.info(
            f"[build_gold] {symbol}: {result.get('records', 0)} feature rows written"
        )
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# JOBS  (pipeline definitions)
# ═══════════════════════════════════════════════════════════════════════════════

@job(
    name="stock_lakehouse_job",
    description=(
        "Full medallion pipeline: Bronze → Silver → Gold. "
        "Ingests raw OHLCV, cleans/validates, engineers features for ML."
    ),
    resource_defs={
        "lakehouse": lakehouse_resource,
        "io_manager": pipeline_io_manager,
    },
    tags={"team": "data", "domain": "finance"},
)
def stock_lakehouse_job(config: LakehouseConfig):
    """
    The main lakehouse pipeline job.

    Flow: ingest_bronze → transform_silver → validate_quality → build_gold

    Each op's output becomes the input to the next via IO manager.
    If any op fails, downstream ops don't run (fail-fast).
    """
    bronze_results = ingest_bronze(config)
    silver_results = transform_silver(config)
    quality_results = validate_quality(config)
    gold_results = build_gold(config)
    return gold_results


# ═══════════════════════════════════════════════════════════════════════════════
# ASSETS  (declarative data outputs - alternative to graph-based jobs)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_bronze_asset(symbol: str) -> AssetsDefinition:
    """Factory: create one Bronze asset per symbol."""

    @op(name=f"bronze_asset_{symbol.lower()}", tags={"symbol": symbol, "layer": "bronze"})
    def bronze_op(cfg: LakehouseConfig) -> dict:
        return ingest_symbol(symbol=symbol, interval=cfg.interval, source_name=cfg.source_name)

    return AssetsDefinition.from_op(
        bronze_op,
        keys_by_output_name={"result": AssetKey(["bronze", symbol.upper()])},
    )


def _make_silver_asset(symbol: str) -> AssetsDefinition:
    """Factory: create one Silver asset per symbol."""

    bronze_key = AssetKey(["bronze", symbol.upper()])

    @op(name=f"silver_asset_{symbol.lower()}", tags={"symbol": symbol, "layer": "silver"})
    def silver_op(cfg: LakehouseConfig) -> dict:
        # Asset is automatically provided as input by Dagster
        return transform_to_silver(symbol)

    return AssetsDefinition.from_op(
        silver_op,
        keys_by_output_name={"result": AssetKey(["silver", symbol.upper()])},
        deps=[AssetDep(bronze_key)],
    )


def _make_gold_asset(symbol: str) -> AssetsDefinition:
    """Factory: create one Gold asset per symbol."""

    silver_key = AssetKey(["silver", symbol.upper()])

    @op(name=f"gold_asset_{symbol.lower()}", tags={"symbol": symbol, "layer": "gold"})
    def gold_op(cfg: LakehouseConfig) -> dict:
        return build_gold_layer(symbol)

    return AssetsDefinition.from_op(
        gold_op,
        keys_by_output_name={"result": AssetKey(["gold", symbol.upper()])},
        deps=[AssetDep(silver_key)],
    )


# Build all assets for configured symbols
def _build_all_assets(symbols: list[str]) -> list[AssetsDefinition]:
    assets = []
    for symbol in symbols:
        assets.append(_make_bronze_asset(symbol))
        assets.append(_make_silver_asset(symbol))
        assets.append(_make_gold_asset(symbol))
    return assets


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULES  (automated triggers)
# ═══════════════════════════════════════════════════════════════════════════════

@schedule(
    name="daily_lakehouse_pipeline",
    cron_schedule="0 18 * * 1-5",  # Weekdays at 6 PM (after market close)
    description=(
        "Run the full medallion pipeline daily after US market close. "
        "Weekdays only (Mon-Fri) since no new data on weekends."
    ),
    job=stock_lakehouse_job,
    execution_timezone="America/New_York",
)
def daily_lakehouse_schedule(context) -> RunConfig:
    """
    Daily schedule for production pipeline runs.

    Why 6 PM ET?
    - Market closes at 4 PM ET
    - Gives 2 hours for end-of-day data to settle
    - Avoids overlap with after-hours trading

    In production you'd add:
    - Alerting on failures (Slack/PagerDuty)
    - Backfill for missed runs
    - Conditional execution (skip holidays)
    """
    return RunConfig(
        ops={
            "ingest_bronze": LakehouseConfig(
                symbols=["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"],
                interval="1d",
            )
        }
    )


@schedule(
    name="hourly_bronze_refresh",
    cron_schedule="0 * * * *",  # Every hour
    description="Ingest latest data into Bronze every hour for intraday symbols.",
    job=stock_lakehouse_job,
    execution_timezone="UTC",
)
def hourly_bronze_schedule(context) -> RunConfig:
    """Hourly refresh for intraday data (interval=1h) when needed."""
    return RunConfig(
        ops={
            "ingest_bronze": LakehouseConfig(
                symbols=["AAPL", "MSFT"],
                interval="1h",
            )
        }
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ASSET JOB  (asset-based pipeline - modern alternative)
# ═══════════════════════════════════════════════════════════════════════════════

# Create asset job that materializes all medallion assets
lakehouse_asset_job = define_asset_job(
    name="stock_lakehouse_asset_job",
    selection=AssetSelection.all(),
    description="Asset-based lakehouse pipeline (modern Dagster approach).",
    tags={"team": "data", "domain": "finance"},
)


# ═══════════════════════════════════════════════════════════════════════════════
# REPOSITORY  (exposes all jobs/schedules/assets to Dagster UI)
# ═══════════════════════════════════════════════════════════════════════════════

@repository(
    name="stock_lakehouse",
    packages=[
        # Expose jobs
        stock_lakehouse_job,
        # Expose asset job
        lakehouse_asset_job,
        # Expose schedules
        daily_lakehouse_schedule,
        hourly_bronze_schedule,
    ],
)
def stock_lakehouse_repository():
    """
    Dagster repository exposing all pipeline definitions.

    This is the entry point Dagster daemon/webserver reads on startup.
    All jobs, schedules, and assets defined here appear in the UI.

    Usage:
        dagster-webserver:  http://localhost:3000
        dagster-daemon:     Runs schedules, sensors, execution
    """
    return [
        stock_lakehouse_job,
        lakehouse_asset_job,
        daily_lakehouse_schedule,
        hourly_bronze_schedule,
    ]
