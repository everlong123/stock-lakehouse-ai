"""API endpoints for Lakehouse pipeline management."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.constants import SUPPORTED_SYMBOLS
from app.core.logging_config import get_logger
from app.lakehouse.pipeline import LakehousePipeline, PipelineConfig, PipelineRun, run_pipeline

logger = get_logger(__name__)

router = APIRouter(prefix="/pipeline", tags=["lakehouse"])


# ─── Request/Response Models ────────────────────────────────────────────────────


class PipelineRunRequest(BaseModel):
    """Request to run the pipeline."""
    symbols: list[str] | None = Field(
        default=None,
        description="List of symbols. If None, uses all supported symbols."
    )
    use_minio: bool = Field(
        default=False,
        description="Use MinIO storage backend instead of local."
    )
    skip_silver: bool = Field(
        default=False,
        description="Skip Silver transformation."
    )
    skip_gold: bool = Field(
        default=False,
        description="Skip Gold feature engineering."
    )
    interval: str = Field(
        default="1d",
        description="Data interval: 1d, 1h, 15m, 5m"
    )
    lookback_days: int = Field(
        default=730,
        ge=1,
        le=3650,
        description="Number of days of historical data to fetch."
    )


class PipelineRunResponse(BaseModel):
    """Response from pipeline run."""
    run_id: str
    status: str
    started_at: str
    completed_at: str | None
    bronze_records: int
    silver_records: int
    gold_records: int
    duplicates_removed: int
    invalid_records: int
    quality_score: float
    symbols_processed: list[str]
    storage_backend: str
    errors: list[str]
    warnings: list[str]


class LayerInfoResponse(BaseModel):
    """Information about data in a layer."""
    symbol: str
    bronze: dict
    silver: dict
    gold: dict
    storage_backend: str


class StorageStatusResponse(BaseModel):
    """Storage backend status."""
    backend: str
    available: bool
    details: dict | None = None


# ─── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/run", response_model=PipelineRunResponse)
async def run_lakehouse_pipeline(request: PipelineRunRequest) -> PipelineRunResponse:
    """
    Run the complete Lakehouse pipeline (Bronze → Silver → Gold).
    
    This ingests raw data from sources, cleans it, and engineers features.
    """
    # Build config
    symbols = request.symbols or SUPPORTED_SYMBOLS
    config = PipelineConfig(
        use_minio=request.use_minio,
        symbols=symbols,
        interval=request.interval,
        lookback_days=request.lookback_days,
        skip_silver=request.skip_silver,
        skip_gold=request.skip_gold,
    )
    
    # Run pipeline
    logger.info(f"Starting pipeline for {len(symbols)} symbols")
    pipeline = LakehousePipeline(config)
    result = pipeline.run(symbols)
    
    # Convert to response
    return PipelineRunResponse(**result.to_dict())


@router.get("/run/{run_id}", response_model=PipelineRunResponse)
async def get_pipeline_run(run_id: str) -> PipelineRunResponse:
    """Get status of a pipeline run (placeholder - run history not persisted yet)."""
    raise HTTPException(
        status_code=501,
        detail="Run history not implemented. Re-run the pipeline to get fresh results."
    )


@router.get("/layers/{symbol}", response_model=LayerInfoResponse)
async def get_layer_info(
    symbol: str,
    use_minio: bool = Query(default=False, description="Use MinIO storage backend.")
) -> LayerInfoResponse:
    """
    Get information about data in all layers for a symbol.
    
    Shows record counts and availability for Bronze, Silver, and Gold layers.
    """
    config = PipelineConfig(use_minio=use_minio)
    pipeline = LakehousePipeline(config)
    info = pipeline.get_layer_info(symbol.upper())
    return LayerInfoResponse(**info)


@router.get("/data/{symbol}")
async def get_lakehouse_data(
    symbol: str,
    layer: Literal["bronze", "silver", "gold"] = Query(default="gold"),
    limit: int = Query(default=100, ge=1, le=10000),
    use_minio: bool = Query(default=False),
) -> dict:
    """
    Get data from a specific layer.
    
    Returns up to `limit` rows sorted by timestamp.
    """
    config = PipelineConfig(use_minio=use_minio)
    pipeline = LakehousePipeline(config)
    
    try:
        df = pipeline.get_data(symbol.upper(), layer)
        if df.empty:
            return {
                "symbol": symbol.upper(),
                "layer": layer,
                "count": 0,
                "data": [],
            }
        
        # Sort and limit
        df = df.sort_values("timestamp", ascending=False).head(limit)
        
        # Convert to dict, handling datetime serialization
        records = []
        for _, row in df.iterrows():
            record = {}
            for col, val in row.items():
                if hasattr(val, 'isoformat'):
                    record[col] = val.isoformat()
                else:
                    record[col] = val
            records.append(record)
        
        return {
            "symbol": symbol.upper(),
            "layer": layer,
            "count": len(records),
            "data": records,
        }
    except Exception as e:
        logger.error(f"Failed to get data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage/status", response_model=StorageStatusResponse)
async def get_storage_status() -> StorageStatusResponse:
    """Get status of the storage backend."""
    from app.lakehouse import get_storage_backend
    
    try:
        storage = get_storage_backend()
        health = storage.health()
        return StorageStatusResponse(
            backend=health.get("backend", "unknown"),
            available=health.get("available", False),
            details=health,
        )
    except Exception as e:
        return StorageStatusResponse(
            backend="unknown",
            available=False,
            details={"error": str(e)},
        )


@router.get("/symbols/supported")
async def get_supported_symbols() -> dict:
    """Get list of supported symbols."""
    return {
        "symbols": SUPPORTED_SYMBOLS,
        "count": len(SUPPORTED_SYMBOLS),
        "intervals": ["1d", "1h", "15m", "5m"],
    }


@router.post("/storage/initialize")
async def initialize_storage(
    use_minio: bool = Query(default=True),
) -> dict:
    """
    Initialize storage buckets/paths.
    
    For MinIO: creates buckets if they don't exist.
    For local: creates directories if they don't exist.
    """
    from app.lakehouse import MinioStorageBackend
    
    try:
        if use_minio:
            storage = MinioStorageBackend()
            health = storage.health()
            if health.get("available"):
                return {
                    "backend": "minio",
                    "status": "initialized",
                    "buckets": list(set(storage._bucket(l) for l in ["bronze", "silver", "gold"])),
                }
            return {
                "backend": "minio",
                "status": "failed",
                "error": "MinIO not available",
            }
        return {
            "backend": "local",
            "status": "initialized",
        }
    except Exception as e:
        logger.error(f"Storage initialization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
