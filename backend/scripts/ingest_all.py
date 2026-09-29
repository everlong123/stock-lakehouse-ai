"""
Comprehensive Data Ingestion Script

Thu thập dữ liệu chứng khoán toàn diện:
- 60+ symbols
- 5 năm daily data (1d interval)
- 1 năm hourly data (1h interval)
- Xử lý rate limit tự động
- Retry logic thông minh
- Progress tracking

Chạy: python scripts/ingest_all.py [--interval 1d] [--lookback 1825]
"""

from __future__ import annotations

import sys
import time
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Generator
import logging

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from tqdm import tqdm

from app.core.config import settings
from app.core.constants import (
    SUPPORTED_SYMBOLS,
    MARKET_INDEXES,
    CRYPTO_SYMBOLS,
    ALL_SYMBOLS,
    OHLCV_COLUMNS,
)
from app.data_sources.factory import get_data_provider
from app.lakehouse import BronzeLayer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class IngestConfig:
    """Configuration for data ingestion."""
    
    # Symbols to ingest
    symbols: list[str] = field(default_factory=lambda: ALL_SYMBOLS)
    
    # Intervals and lookback
    intervals: list[str] = field(default_factory=lambda: ["1d"])
    
    # Lookback in days per interval
    lookback_days: dict[str, int] = field(default_factory=lambda: {
        "1d": 1825,   # 5 years
        "1h": 365,     # 1 year
        "15m": 30,     # 30 days
        "5m": 7,       # 7 days
    })
    
    # Rate limiting
    request_delay: float = 0.5  # seconds between requests
    max_retries: int = 3
    retry_delay: float = 5.0
    
    # Performance
    batch_size: int = 5  # concurrent requests
    verbose: bool = True


@dataclass
class IngestStats:
    """Statistics for ingestion run."""
    
    total_symbols: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    
    total_records: int = 0
    total_duplicates: int = 0
    
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    
    def duration_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now() - self.start_time).total_seconds()
    
    def summary(self) -> dict:
        return {
            "total_symbols": self.total_symbols,
            "successful": self.successful,
            "failed": self.failed,
            "skipped": self.skipped,
            "total_records": self.total_records,
            "total_duplicates": self.total_duplicates,
            "duration_seconds": self.duration_seconds(),
            "records_per_second": self.total_records / max(1, self.duration_seconds()),
        }


class DataIngestor:
    """Handles stock data fetching with rate limit handling."""
    
    def __init__(self, config: IngestConfig):
        self.config = config
        self._provider = get_data_provider()  # Uses DATA_SOURCE from settings
    
    def fetch(
        self,
        symbol: str,
        interval: str = "1d",
        lookback_days: int = 1825,
    ) -> pd.DataFrame | None:
        """Fetch data from configured provider with retries."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)
        
        for attempt in range(self.config.max_retries):
            try:
                df = self._provider.get_historical_data(
                    symbol=symbol,
                    start=start,
                    end=end,
                    interval=interval,
                )
                
                if df is None or df.empty:
                    logger.debug(f"No data for {symbol} {interval}")
                    return None
                
                return df
                
            except Exception as e:
                if attempt < self.config.max_retries - 1:
                    wait = self.config.retry_delay * (2 ** attempt)
                    logger.warning(f"{symbol} {interval}: retry {attempt + 1} after {wait}s - {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"{symbol} {interval}: failed after {self.config.max_retries} retries - {e}")
        
        return None


def estimate_data_size(
    symbols: list[str], 
    intervals: dict[str, int]
) -> dict:
    """Estimate data size for given configuration."""
    estimates = {}
    total_rows = 0
    
    for interval, days in intervals.items():
        bars_per_day = {
            "1d": 1,
            "1h": 7,    # 6.5 hours trading
            "15m": 78,  # 6.5 hours * 4 (15min bars)
            "5m": 78,   # Same
        }.get(interval, 1)
        
        rows = len(symbols) * days * bars_per_day
        total_rows += rows
        
        # Estimate size (rough: ~100 bytes per row in Parquet)
        size_mb = rows * 100 / (1024 * 1024)
        estimates[interval] = {
            "days": days,
            "bars_per_day": bars_per_day,
            "rows_per_symbol": days * bars_per_day,
            "total_rows": rows,
            "estimated_size_mb": round(size_mb, 2),
        }
    
    return {
        "symbols": len(symbols),
        "intervals": estimates,
        "total_rows": total_rows,
        "total_estimated_mb": round(sum(e["estimated_size_mb"] for e in estimates.values()), 2),
        "total_estimated_gb": round(sum(e["estimated_size_mb"] for e in estimates.values()) / 1024, 3),
    }


def ingest_symbol_interval(
    symbol: str,
    interval: str,
    lookback_days: int,
    bronze,
    delay: float,
) -> dict:
    """Ingest a single symbol-interval combination."""
    result = {
        "symbol": symbol,
        "interval": interval,
        "status": "pending",
        "records": 0,
        "duplicates": 0,
        "error": None,
    }
    
    try:
        # Check if existing data
        existing = bronze.read(symbol)
        
        if not existing.empty:
            existing_dates = set(existing["timestamp"].dt.date)
            logger.debug(f"{symbol} {interval}: {len(existing)} records exist")
        
        # Fetch new data
        ingestor = DataIngestor(IngestConfig())
        df = ingestor.fetch(symbol, interval, lookback_days)
        
        if df is None or df.empty:
            result["status"] = "no_data"
            return result
        
        # Write to Bronze
        metadata = bronze.append(df, lineage={
            "source": "alpha_vantage",
            "symbol": symbol,
            "interval": interval,
            "lookback_days": lookback_days,
        })
        
        result["records"] = metadata["records_written"]
        result["duplicates"] = metadata["duplicate_count"]
        result["status"] = "success"
        
        # Rate limit delay
        time.sleep(delay)
        
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


def run_ingestion(config: IngestConfig) -> IngestStats:
    """Run the full ingestion process."""
    stats = IngestStats()
    stats.total_symbols = len(config.symbols)
    
    logger.info("=" * 60)
    logger.info("DATA INGESTION STARTED")
    logger.info("=" * 60)
    logger.info(f"Symbols: {len(config.symbols)}")
    logger.info(f"Intervals: {config.intervals}")
    logger.info(f"Lookback: {config.lookback_days}")
    
    # Estimate size
    size_estimate = estimate_data_size(config.symbols, config.lookback_days)
    logger.info(f"Estimated size: {size_estimate['total_estimated_mb']} MB")
    logger.info("=" * 60)
    
    # Initialize lakehouse
    bronze = BronzeLayer()
    
    # Calculate total tasks
    total_tasks = len(config.symbols) * len(config.intervals)
    
    logger.info(f"Total tasks: {total_tasks}")
    
    # Progress bar
    pbar = tqdm(total=total_tasks, desc="Ingesting", unit="symbol-interval")
    
    # Process in batches
    for interval in config.intervals:
        lookback = config.lookback_days.get(interval, 1825)
        
        # Filter existing symbols for this interval
        symbols_to_fetch = []
        for symbol in config.symbols:
            # Check existing data
            try:
                existing = bronze.read(symbol)
                if existing.empty:
                    symbols_to_fetch.append(symbol)
                else:
                    existing_interval = existing.iloc[0]["timestamp"] - existing.iloc[-1]["timestamp"]
                    # If we have enough data, skip
                    if len(existing) >= lookback * 0.9:
                        stats.skipped += 1
                        pbar.update(1)
                        continue
                    symbols_to_fetch.append(symbol)
            except Exception:
                symbols_to_fetch.append(symbol)
        
        logger.info(f"\n{interval}: Fetching {len(symbols_to_fetch)}/{len(config.symbols)} symbols")
        
        # Process with thread pool
        with ThreadPoolExecutor(max_workers=config.batch_size) as executor:
            futures = {}
            
            for symbol in symbols_to_fetch:
                future = executor.submit(
                    ingest_symbol_interval,
                    symbol,
                    interval,
                    lookback,
                    bronze,
                    config.request_delay,
                )
                futures[future] = (symbol, interval)
            
            for future in as_completed(futures):
                symbol, interval = futures[future]
                
                try:
                    result = future.result()
                    
                    if result["status"] == "success":
                        stats.successful += 1
                        stats.total_records += result["records"]
                        stats.total_duplicates += result["duplicates"]
                    elif result["status"] == "error":
                        stats.failed += 1
                        stats.errors.append(f"{symbol} {interval}: {result['error']}")
                    else:
                        stats.skipped += 1
                        
                except Exception as e:
                    stats.failed += 1
                    stats.errors.append(f"{symbol} {interval}: {e}")
                
                pbar.update(1)
    
    pbar.close()
    stats.end_time = datetime.now()
    
    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Ingest stock data from Yahoo Finance")
    parser.add_argument("--interval", "-i", default="1d", choices=["1d", "1h", "15m", "5m", "all"])
    parser.add_argument("--lookback", "-l", type=int, default=None, help="Lookback days (overrides default)")
    parser.add_argument("--symbols", "-s", nargs="*", default=None, help="Specific symbols to ingest")
    parser.add_argument("--batch", "-b", type=int, default=5, help="Concurrent requests")
    parser.add_argument("--delay", "-d", type=float, default=0.5, help="Delay between requests")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")
    
    args = parser.parse_args()
    
    # Determine intervals
    if args.interval == "all":
        intervals = ["1d", "1h"]  # Skip 15m/5m unless explicitly requested
    else:
        intervals = [args.interval]
    
    # Determine symbols
    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
    else:
        symbols = ALL_SYMBOLS
    
    # Lookback override
    lookback = {interval: args.lookback for interval in intervals} if args.lookback else None
    
    # Create config
    config = IngestConfig(
        symbols=symbols,
        intervals=intervals,
        lookback_days=lookback or {
            "1d": 1825,   # 5 years
            "1h": 365,     # 1 year
            "15m": 30,     # 30 days
            "5m": 7,       # 7 days
        },
        batch_size=args.batch,
        request_delay=args.delay,
        verbose=not args.quiet,
    )
    
    # Run ingestion
    stats = run_ingestion(config)
    
    # Print summary
    logger.info("=" * 60)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Duration: {stats.duration_seconds():.1f} seconds")
    logger.info(f"Successful: {stats.successful}")
    logger.info(f"Failed: {stats.failed}")
    logger.info(f"Skipped: {stats.skipped}")
    logger.info(f"Total records: {stats.total_records:,}")
    logger.info(f"Duplicates: {stats.total_duplicates:,}")
    
    if stats.errors:
        logger.warning(f"\nErrors ({len(stats.errors)}):")
        for err in stats.errors[:10]:
            logger.warning(f"  - {err}")
        if len(stats.errors) > 10:
            logger.warning(f"  ... and {len(stats.errors) - 10} more")
    
    return stats


if __name__ == "__main__":
    main()
