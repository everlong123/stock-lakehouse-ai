"""End-to-end historical data ingestion for the Stock Lakehouse.

This script fetches OHLCV bars from the provider configured via
``DATA_SOURCE`` (defaults to ``yfinance``) and writes them through the full
Medallion pipeline:

    raw payload  -> Bronze (Parquet/Iceberg)
                  -> Silver (cleaned, quality checked)
                  -> Gold   (technical features + targets)

Usage examples::

    # Default (DATA_SOURCE from .env, all supported symbols, 5y daily)
    python scripts/ingest_historical.py

    # Specific provider and ticker
    python scripts/ingest_historical.py --source finnhub --symbols AAPL,MSFT,GOOGL
    python scripts/ingest_historical.py --source yfinance --symbols AAPL --interval 1h

    # Different lookback (default: 730 days for daily, 365 for hourly)
    python scripts/ingest_historical.py --interval 1d --lookback 1825

Both ``yfinance`` (the official ``yfinance`` package) and ``finnhub`` are
supported - everything uses the free tier (no paid subscription needed).
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from app.core.constants import ALL_SYMBOLS, SUPPORTED_SYMBOLS
from app.core.logging_config import get_logger
from app.data_sources.factory import get_data_provider
from app.lakehouse import BronzeLayer, GoldLayer, SilverLayer
from app.lakehouse.pipeline import PipelineConfig, LakehousePipeline

logger = get_logger(__name__)


# Free-tier-aware defaults (sensible lookback per interval).
# Yahoo Finance Free tier maxes at ~10y for daily bars; Finnhub Free tier
# caps 1d at ~10 years as well. We pick the larger window so the resulting
# dataset always exceeds the project's "5+ year" requirement.
INTERVAL_LOOKBACK = {
    "1d": 3650,    # ~10 years (Yahoo + Finnhub both support this on Free tier)
    "1h": 730,     # 2 years
    "15m": 60,     # 2 months (Finnhub caps 15m at ~30d, Yahoo at ~60d)
    "5m": 60,      # 2 months
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest historical OHLCV into the Medallion Lakehouse.",
    )
    parser.add_argument(
        "--source",
        default=None,
        choices=["yfinance", "yfinance_direct", "finnhub", "alpha_vantage", "web_scraper", "multi_source"],
        help="Override the data source. Defaults to DATA_SOURCE in .env.",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help=(
            "Comma-separated symbols to ingest. When omitted, uses the "
            "diverse 60+ symbol list from app.core.constants."
        ),
    )
    parser.add_argument(
        "--interval",
        default="1d",
        choices=list(INTERVAL_LOOKBACK.keys()),
        help="Bar interval (default: 1d).",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=None,
        help="Override lookback days (uses INTERVAL_LOOKBACK otherwise).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of symbols to ingest (useful for smoke tests).",
    )
    parser.add_argument(
        "--skip-silver",
        action="store_true",
        help="Skip the Silver cleaning layer (Bronze only).",
    )
    parser.add_argument(
        "--skip-gold",
        action="store_true",
        help="Skip the Gold feature layer (Bronze + Silver only).",
    )
    parser.add_argument(
        "--use-minio",
        action="store_true",
        help="Force MinIO as the storage backend (overrides STORAGE_BACKEND).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce log verbosity.",
    )
    return parser.parse_args(argv)


def resolve_symbols(raw: str | None, limit: int | None) -> list[str]:
    if raw:
        symbols = [item.strip().upper() for item in raw.split(",") if item.strip()]
    else:
        symbols = list(ALL_SYMBOLS or SUPPORTED_SYMBOLS)
    if limit:
        symbols = symbols[:limit]
    return symbols


def fetch_dataframe(
    provider,
    symbol: str,
    interval: str,
    lookback_days: int,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> pd.DataFrame | None:
    """Fetch OHLCV for ``symbol`` with retry logic."""

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    for attempt in range(max_retries):
        try:
            frame = provider.get_historical_data(
                symbol=symbol,
                start=start,
                end=end,
                interval=interval,
            )
            if frame is None or frame.empty:
                logger.warning("No data returned for %s (%s)", symbol, interval)
                return None
            return frame
        except Exception as exc:  # noqa: BLE001 - we want to log anything
            wait = retry_delay * (2 ** attempt)
            logger.warning(
                "Fetch %s %s failed (attempt %s/%s): %s. Retrying in %.1fs",
                symbol,
                interval,
                attempt + 1,
                max_retries,
                exc,
                wait,
            )
            time.sleep(wait)
    logger.error("Giving up on %s %s after %s retries", symbol, interval, max_retries)
    return None


def run(args: argparse.Namespace) -> dict[str, dict[str, int]]:
    """Run the ingestion pipeline. Returns ``{symbol: {bronze, silver, gold}}``."""

    interval = args.interval
    lookback = args.lookback or INTERVAL_LOOKBACK.get(interval, 730)
    symbols = resolve_symbols(args.symbols, args.limit)

    logger.info("=" * 70)
    logger.info("HISTORICAL DATA INGESTION")
    logger.info("Source:      %s", args.source or "from DATA_SOURCE (.env)")
    logger.info("Symbols:     %s (%d total)", symbols[:5] + (["..."] if len(symbols) > 5 else []), len(symbols))
    logger.info("Interval:    %s", interval)
    logger.info("Lookback:    %s days", lookback)
    logger.info("MinIO:       %s", args.use_minio)
    logger.info("=" * 70)

    provider = get_data_provider(args.source)
    logger.info("Selected provider: %s", provider.source_name)

    # Validate the provider can talk to its API (cheap guard against typos).
    if hasattr(provider, "health_check") and not provider.health_check():
        logger.warning(
            "%s reports it cannot reach the data API. Ingestion may fail.",
            provider.source_name,
        )

    bronze = BronzeLayer()
    silver = SilverLayer() if not args.skip_silver else None
    gold = GoldLayer() if not args.skip_gold else None

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback)

    summary: dict[str, dict[str, int]] = {}
    success = failed = 0

    for index, symbol in enumerate(symbols, start=1):
        logger.info("[%d/%d] Ingesting %s", index, len(symbols), symbol)

        frame = fetch_dataframe(provider, symbol, interval, lookback)
        if frame is None:
            failed += 1
            summary[symbol] = {"bronze": 0, "silver": 0, "gold": 0, "status": "no_data"}
            continue

        try:
            bronze_meta = bronze.append(
                frame,
                lineage={
                    "source": provider.source_name,
                    "symbol": symbol,
                    "interval": interval,
                    "lookback_days": lookback,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "task": "ingest_historical",
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Bronze write failed for %s: %s", symbol, exc)
            failed += 1
            summary[symbol] = {"bronze": 0, "silver": 0, "gold": 0, "status": "bronze_error"}
            continue

        bronze_records = bronze_meta.get("records_written", len(frame))
        silver_records = 0
        gold_records = 0

        if silver is not None:
            try:
                cleaned, quality = silver.transform(frame)
                if cleaned is not None and not cleaned.empty:
                    silver.write(cleaned, quality)
                    silver_records = quality.get("record_count", len(cleaned))
            except Exception as exc:  # noqa: BLE001
                logger.error("Silver write failed for %s: %s", symbol, exc)

        if gold is not None and silver_records > 0:
            try:
                silver_frame = silver.read(symbol)
                if not silver_frame.empty:
                    gold_frame = gold.transform(silver_frame)
                    if gold_frame is not None and not gold_frame.empty:
                        gold.write(gold_frame)
                        gold_records = len(gold_frame)
            except Exception as exc:  # noqa: BLE001
                logger.error("Gold write failed for %s: %s", symbol, exc)

        summary[symbol] = {
            "bronze": bronze_records,
            "silver": silver_records,
            "gold": gold_records,
            "status": "success",
        }
        success += 1
        logger.info(
            "[OK] %s bronze=%d silver=%d gold=%d",
            symbol,
            bronze_records,
            silver_records,
            gold_records,
        )

    logger.info("=" * 70)
    logger.info("INGESTION COMPLETE")
    logger.info(
        "Success: %d | Failed: %d | Total symbols: %d",
        success,
        failed,
        len(symbols),
    )
    logger.info("Bronze total records: %d",
                sum(item["bronze"] for item in summary.values()))
    logger.info("Silver total records: %d",
                sum(item["silver"] for item in summary.values()))
    logger.info("Gold   total records: %d",
                sum(item["gold"] for item in summary.values()))
    logger.info("=" * 70)
    return summary


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.quiet:
        import logging

        logging.getLogger().setLevel(logging.WARNING)
    run(args)


if __name__ == "__main__":
    main()