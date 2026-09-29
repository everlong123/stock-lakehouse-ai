"""
Lakehouse Data Pipeline - Medallion Architecture Implementation

Orchestrates the complete data flow:
    ┌─────────────┐
    │ Data Source │ (Yahoo Finance, VnExpress RSS)
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │   BRONZE    │ ← Raw ingestion, schema validation, lineage tracking
    │  (Parquet)  │   Partitioned by: symbol, year, month
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │   SILVER    │ ← Cleaning, deduplication, OHLC validation
    │  (Parquet)  │   Quality checks, error logging
    └──────┬──────┘
           ▼
    ┌─────────────┐
    │    GOLD     │ ← Feature engineering, targets, ML-ready
    │  (Parquet)  │   Technical indicators, lags, labels
    └─────────────┘
           ▼
    ┌─────────────┐
    │   Analytics │ (Dashboard, ML Training, AI Agent)
    └─────────────┘

Storage Backend:
- MinIO (S3-compatible) when use_spark=true or use_iceberg=true
- Local filesystem as fallback
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

import pandas as pd

from app.core.config import settings
from app.core.logging_config import get_logger
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.silver import SilverLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.storage_factory import get_storage_backend

logger = get_logger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for lakehouse pipeline."""
    
    # Storage
    use_minio: bool = False
    use_iceberg: bool = False
    use_spark: bool = False
    
    # Processing
    symbols: list[str] | None = None
    interval: str = "1d"
    lookback_days: int = 730
    
    # Quality
    skip_silver: bool = False
    skip_gold: bool = False
    
    # Source
    data_source: str = "yfinance"


@dataclass
class PipelineRun:
    """Record of a pipeline execution."""
    
    run_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    status: str = "running"  # running, success, failed
    
    # Counts
    bronze_records: int = 0
    silver_records: int = 0
    gold_records: int = 0
    
    # Quality
    duplicates_removed: int = 0
    invalid_records: int = 0
    quality_score: float = 0.0
    
    # Errors
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    # Metadata
    symbols_processed: list[str] = field(default_factory=list)
    storage_backend: str = "unknown"
    
    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "bronze_records": self.bronze_records,
            "silver_records": self.silver_records,
            "gold_records": self.gold_records,
            "duplicates_removed": self.duplicates_removed,
            "invalid_records": self.invalid_records,
            "quality_score": self.quality_score,
            "errors": self.errors,
            "warnings": self.warnings,
            "symbols_processed": self.symbols_processed,
            "storage_backend": self.storage_backend,
        }


class LakehousePipeline:
    """
    Orchestrates the complete Medallion Lakehouse pipeline.
    
    Bronze → Silver → Gold with proper error handling and quality tracking.
    """
    
    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        
        # Initialize storage backend
        if self.config.use_minio:
            try:
                from app.lakehouse.minio_storage import MinioStorageBackend
                self.storage = MinioStorageBackend()
                self.storage.health()  # Verify connection
                logger.info("Using MinIO storage backend")
            except Exception as e:
                logger.warning(f"MinIO unavailable: {e}, falling back to local")
                self.storage = get_storage_backend()
        else:
            self.storage = get_storage_backend()
        
        # Initialize lakehouse layers
        self.bronze = BronzeLayer(storage=self.storage)
        self.silver = SilverLayer(storage=self.storage)
        self.gold = GoldLayer(storage=self.storage)
        
        self.current_run: PipelineRun | None = None
    
    def run(self, symbols: list[str] | None = None) -> PipelineRun:
        """
        Execute the complete pipeline for given symbols.
        
        Args:
            symbols: List of stock symbols. If None, uses config.symbols or default.
            
        Returns:
            PipelineRun with execution statistics
        """
        import uuid
        
        # Initialize run
        self.current_run = PipelineRun(
            run_id=str(uuid.uuid4())[:8],
            storage_backend=self.storage.backend_name,
        )
        
        symbols = symbols or self.config.symbols or []
        self.current_run.symbols_processed = symbols
        
        logger.info(f"Starting pipeline run {self.current_run.run_id}")
        logger.info(f"Storage backend: {self.storage.backend_name}")
        logger.info(f"Symbols: {symbols}")
        
        try:
            # Step 1: Ingest to Bronze
            self._ingest_bronze(symbols)
            
            # Step 2: Transform to Silver
            if not self.config.skip_silver:
                self._transform_silver(symbols)
            
            # Step 3: Engineer Gold features
            if not self.config.skip_gold:
                self._transform_gold(symbols)
            
            # Calculate quality score
            self._calculate_quality_score()
            
            self.current_run.status = "success"
            self.current_run.completed_at = datetime.now(timezone.utc)
            
            logger.info(f"Pipeline {self.current_run.run_id} completed successfully")
            logger.info(f"  Bronze: {self.current_run.bronze_records} records")
            logger.info(f"  Silver: {self.current_run.silver_records} records")
            logger.info(f"  Gold: {self.current_run.gold_records} records")
            logger.info(f"  Quality: {self.current_run.quality_score:.1f}%")
            
        except Exception as e:
            self.current_run.status = "failed"
            self.current_run.completed_at = datetime.now(timezone.utc)
            self.current_run.errors.append(str(e))
            logger.error(f"Pipeline {self.current_run.run_id} failed: {e}")
        
        return self.current_run
    
    def _ingest_bronze(self, symbols: list[str]) -> None:
        """Ingest raw data from sources to Bronze layer."""
        from app.data_sources import get_data_provider
        
        provider = get_data_provider(self.config.data_source)
        
        total_records = 0
        total_duplicates = 0
        
        # Calculate date range
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=self.config.lookback_days)
        
        for symbol in symbols:
            try:
                # Fetch from source
                frame = provider.get_historical_data(
                    symbol,
                    start=start,
                    end=end,
                    interval=self.config.interval,
                )
                
                if frame.empty:
                    self.current_run.warnings.append(f"No data for {symbol}")
                    continue
                
                # Write to Bronze
                metadata = self.bronze.append(frame, lineage={
                    "source": self.config.data_source,
                    "symbol": symbol,
                    "type": "ohlcv",
                    "interval": self.config.interval,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                })
                
                total_records += metadata["records_written"]
                total_duplicates += metadata["duplicate_count"]
                
                logger.info(f"Bronze: {symbol} - {metadata['records_written']} records")
                
            except Exception as e:
                self.current_run.errors.append(f"Bronze ingest failed for {symbol}: {e}")
                logger.error(f"Bronze ingest failed for {symbol}: {e}")
        
        self.current_run.bronze_records = total_records
        self.current_run.duplicates_removed = total_duplicates
    
    def _transform_silver(self, symbols: list[str]) -> None:
        """Transform Bronze data to Silver layer."""
        total_records = 0
        total_invalid = 0
        
        for symbol in symbols:
            try:
                # Read from Bronze
                bronze_frame = self.bronze.read(symbol)
                
                if bronze_frame.empty:
                    continue
                
                # Transform to Silver
                silver_frame, quality_report = self.silver.transform(bronze_frame)
                
                if silver_frame.empty:
                    self.current_run.warnings.append(f"Silver empty for {symbol}")
                    continue
                
                # Write to Silver
                self.silver.write(silver_frame, quality_report)
                
                total_records += quality_report["record_count"]
                total_invalid += quality_report.get("error_count", 0)
                
                logger.info(f"Silver: {symbol} - {quality_report['record_count']} records, "
                           f"errors: {quality_report.get('error_count', 0)}")
                
            except Exception as e:
                self.current_run.errors.append(f"Silver transform failed for {symbol}: {e}")
                logger.error(f"Silver transform failed for {symbol}: {e}")
        
        self.current_run.silver_records = total_records
        self.current_run.invalid_records = total_invalid
    
    def _transform_gold(self, symbols: list[str]) -> None:
        """Transform Silver data to Gold layer with features."""
        total_records = 0
        
        for symbol in symbols:
            try:
                # Read from Silver
                silver_frame = self.silver.read(symbol)
                
                if silver_frame.empty:
                    continue
                
                # Engineer features
                gold_frame = self.gold.transform(silver_frame)
                
                if gold_frame.empty:
                    self.current_run.warnings.append(f"Gold empty for {symbol}")
                    continue
                
                # Write to Gold
                result = self.gold.write(gold_frame)
                
                total_records += result["records"]
                
                logger.info(f"Gold: {symbol} - {result['records']} records")
                
            except Exception as e:
                self.current_run.errors.append(f"Gold transform failed for {symbol}: {e}")
                logger.error(f"Gold transform failed for {symbol}: {e}")
        
        self.current_run.gold_records = total_records
    
    def _calculate_quality_score(self) -> None:
        """Calculate overall quality score for the pipeline run."""
        # If no bronze records but silver/gold have data, we're processing existing data
        if self.current_run.bronze_records == 0:
            if self.current_run.silver_records > 0:
                # Using existing data
                self.current_run.quality_score = 95.0  # Good score for existing processed data
            else:
                self.current_run.quality_score = 0.0
            return
        
        # Quality factors for fresh ingest
        error_penalty = len(self.current_run.errors) * 10
        duplicate_rate = (
            self.current_run.duplicates_removed / 
            max(1, self.current_run.bronze_records) 
        )
        invalid_rate = (
            self.current_run.invalid_records / 
            max(1, self.current_run.silver_records) 
        )
        
        base_score = 100.0
        base_score -= error_penalty
        base_score -= duplicate_rate * 20
        base_score -= invalid_rate * 30
        
        # Retention score
        if self.current_run.bronze_records > 0:
            retention = self.current_run.gold_records / self.current_run.bronze_records
            if retention < 0.5:
                base_score -= 20
        
        self.current_run.quality_score = max(0.0, min(100.0, base_score))
    
    def get_layer_info(self, symbol: str) -> dict:
        """Get info about data in each layer for a symbol."""
        bronze_count = self.bronze.record_count(symbol)
        silver_count = self.silver.record_count(symbol)
        gold_count = self.gold.record_count(symbol)
        
        return {
            "symbol": symbol,
            "bronze": {
                "records": bronze_count,
                "exists": bronze_count > 0,
            },
            "silver": {
                "records": silver_count,
                "exists": silver_count > 0,
            },
            "gold": {
                "records": gold_count,
                "exists": gold_count > 0,
            },
            "storage_backend": self.storage.backend_name,
        }
    
    def get_data(self, symbol: str, layer: str = "gold") -> pd.DataFrame:
        """Get data from specified layer."""
        if layer == "bronze":
            return self.bronze.read(symbol)
        elif layer == "silver":
            return self.silver.read(symbol)
        elif layer == "gold":
            return self.gold.read(symbol)
        else:
            raise ValueError(f"Unknown layer: {layer}")


# Convenience functions
def run_pipeline(
    symbols: list[str] | None = None,
    use_minio: bool = False,
    skip_silver: bool = False,
    skip_gold: bool = False,
) -> PipelineRun:
    """Run the lakehouse pipeline with given configuration."""
    config = PipelineConfig(
        use_minio=use_minio,
        symbols=symbols,
        skip_silver=skip_silver,
        skip_gold=skip_gold,
    )
    pipeline = LakehousePipeline(config)
    return pipeline.run(symbols)
