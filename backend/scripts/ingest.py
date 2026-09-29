"""
Data Ingestion Script - Snapshot to Bronze Layer

This script fetches data from multiple sources and saves to bronze layer.
Run this periodically or on-demand to refresh the data lake.

Usage:
    python scripts/ingest.py --source yahoo --tickers AAPL,MSFT,GOOGL
    python scripts/ingest.py --source all
    python scripts/ingest.py --mode news
"""

import argparse
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters import (
    YahooFinanceDirectAdapter,
    VnExpressRSSAdapter,
    DataSourceFactory,
    MultiSourceAdapter,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Configuration
BRONZE_DIR = Path(__file__).parent.parent / "data" / "bronze"
DEFAULT_TICKERS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA']


def ensure_bronze_dir():
    """Create bronze directory if not exists"""
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Bronze directory: {BRONZE_DIR}")


def snapshot_prices(tickers: list, sources: list = None) -> dict:
    """
    Fetch and save price data to bronze
    
    Args:
        tickers: List of stock symbols
        sources: List of source names (uses MultiSourceAdapter if multiple)
    
    Returns:
        Dict of {ticker: filepath}
    """
    if sources and len(sources) > 1:
        adapter = MultiSourceAdapter(sources)
    elif sources:
        adapter = DataSourceFactory.create(sources[0])
    else:
        adapter = YahooFinanceDirectAdapter()
    
    results = {}
    
    for ticker in tickers:
        try:
            logger.info(f"Fetching {ticker}...")
            
            df = adapter.fetch_prices(
                ticker,
                interval='1D',
                end=datetime.now().strftime('%Y-%m-%d')
            )
            
            if df.empty:
                logger.warning(f"No data for {ticker}")
                continue
            
            # Save to bronze with timestamp
            filename = f"{ticker.lower()}_prices_{adapter.source_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = BRONZE_DIR / filename
            df.to_csv(filepath, index=False)
            
            results[ticker] = filepath
            logger.info(f"Saved {len(df)} rows for {ticker} -> {filename}")
            
        except Exception as e:
            logger.error(f"Failed to fetch {ticker}: {e}")
    
    return results


def snapshot_news(tickers: list = None, limit: int = 50) -> Path:
    """
    Fetch and save news to bronze
    
    Args:
        tickers: List of tickers (optional, for filtering)
        limit: Max news items per source
    
    Returns:
        Path to saved file
    """
    adapter = MultiSourceAdapter(['vnexpress', 'yahoo'])
    
    logger.info("Fetching news...")
    df = adapter.fetch_news(ticker=None, limit=limit)
    
    if df.empty:
        logger.warning("No news fetched")
        return None
    
    # Save to bronze
    filename = f"news_aggregated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = BRONZE_DIR / filename
    df.to_csv(filepath, index=False)
    
    logger.info(f"Saved {len(df)} news items -> {filename}")
    return filepath


def snapshot_all(tickers: list = None):
    """
    Run full snapshot: prices + news
    """
    ensure_bronze_dir()
    
    if tickers is None:
        tickers = DEFAULT_TICKERS
    
    logger.info("="*60)
    logger.info("STARTING FULL DATA SNAPSHOT")
    logger.info(f"Time: {datetime.now().isoformat()}")
    logger.info(f"Tickers: {tickers}")
    logger.info("="*60)
    
    # Snapshot prices
    logger.info("\n--- SNAPSHOT PRICES ---")
    price_results = snapshot_prices(tickers)
    
    # Snapshot news
    logger.info("\n--- SNAPSHOT NEWS ---")
    news_path = snapshot_news(tickers, limit=100)
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("SNAPSHOT COMPLETE")
    logger.info(f"Prices saved: {len(price_results)} files")
    logger.info(f"News saved: {news_path}")
    logger.info(f"Bronze dir: {BRONZE_DIR}")
    logger.info("="*60)
    
    return price_results, news_path


def list_bronze_files():
    """List all files in bronze layer"""
    ensure_bronze_dir()
    
    files = list(BRONZE_DIR.glob("*.csv"))
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    print(f"\nBronze Layer Files ({len(files)} total):")
    print("-" * 80)
    
    for f in files:
        size_kb = f.stat().st_size / 1024
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        print(f"  {mtime}  {size_kb:>8.1f} KB  {f.name}")
    
    return files


def main():
    parser = argparse.ArgumentParser(description='Data Ingestion to Bronze Layer')
    
    parser.add_argument('--source', '-s', nargs='+', 
                        choices=['yahoo', 'vnexpress', 'all'],
                        default=['yahoo'],
                        help='Data source(s) to use')
    
    parser.add_argument('--tickers', '-t', nargs='+',
                        default=DEFAULT_TICKERS,
                        help='Stock tickers to fetch')
    
    parser.add_argument('--mode', '-m', 
                        choices=['prices', 'news', 'all'],
                        default='all',
                        help='Data mode to fetch')
    
    parser.add_argument('--list', '-l', action='store_true',
                        help='List bronze layer files')
    
    args = parser.parse_args()
    
    # Ensure bronze dir
    ensure_bronze_dir()
    
    # List mode
    if args.list:
        list_bronze_files()
        return
    
    # Determine sources
    if 'all' in args.source:
        sources = ['yahoo', 'vnexpress']
    else:
        sources = args.source
    
    # Run snapshot
    if args.mode == 'all':
        snapshot_all(args.tickers)
    elif args.mode == 'prices':
        snapshot_prices(args.tickers, sources)
    elif args.mode == 'news':
        snapshot_news(args.tickers)


if __name__ == '__main__':
    main()
