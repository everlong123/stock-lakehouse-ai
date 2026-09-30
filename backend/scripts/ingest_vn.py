"""Dedicated VN stock ingestion with strict quality validation.

This script:
1. Pulls historical OHLCV from SSI iBoard public API for every VN ticker
   in :data:`VN_HOSE_SYMBOLS`.
2. Pushes the data through the Medallion pipeline (Bronze -> Silver -> Gold).
3. After each symbol it computes a quality report:
   - row count
   - span (first/last date + years)
   - missing / OHLC consistency checks
   - price-range sanity (no negatives, high >= low)
4. Writes a per-symbol CSV report + a single JSON summary.

The output is designed to make it easy to confirm the project stores REAL
Vietnamese market data with full historical depth.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from app.core.constants import VN_HOSE_SYMBOLS
from app.core.logging_config import get_logger
from app.data_sources.ssi_vn_provider import SSIVNProvider
from app.lakehouse import BronzeLayer, GoldLayer, SilverLayer

logger = get_logger(__name__)


REPORT_DIR = ROOT / "docs" / "vn_quality_reports"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Vietnamese stocks (SSI iBoard) with quality report.",
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated VN symbols. Defaults to all VN_HOSE_SYMBOLS.",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=3650,
        help="Days of history to fetch (default: 3650 ~ 10 years).",
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
        help="Force MinIO storage backend.",
    )
    parser.add_argument(
        "--no-pipeline",
        action="store_true",
        help="Only fetch + report quality; do not write to Bronze/Silver/Gold.",
    )
    return parser.parse_args(argv)


def resolve_symbols(raw: str | None) -> list[str]:
    if raw:
        return [item.strip().upper() for item in raw.split(",") if item.strip()]
    return list(VN_HOSE_SYMBOLS)


def quality_report(frame: pd.DataFrame, symbol: str) -> dict:
    """Compute a quality summary for a symbol's bronze frame."""
    if frame.empty:
        return {
            "symbol": symbol,
            "rows": 0,
            "status": "empty",
            "issues": ["provider returned no rows"],
        }

    issues: list[str] = []
    metrics: dict = {"symbol": symbol}

    metrics["rows"] = int(len(frame))
    metrics["first_date"] = frame["timestamp"].min().date().isoformat()
    metrics["last_date"] = frame["timestamp"].max().date().isoformat()
    span_days = (frame["timestamp"].max() - frame["timestamp"].min()).days
    metrics["span_days"] = int(span_days)
    metrics["span_years"] = round(span_days / 365.25, 2)

    # OHLC consistency
    bad_high_low = ((frame["high"] < frame["low"])).sum()
    bad_close_range = (
        (frame["close"] < frame["low"]) | (frame["close"] > frame["high"])
    ).sum()
    bad_open_range = (
        (frame["open"] < frame["low"]) | (frame["open"] > frame["high"])
    ).sum()
    neg_prices = (
        (frame["open"] < 0) | (frame["high"] < 0) | (frame["low"] < 0) | (frame["close"] < 0)
    ).sum()
    zero_volume = (frame["volume"] <= 0).sum()

    metrics["bad_high_low"] = int(bad_high_low)
    metrics["bad_close_range"] = int(bad_close_range)
    metrics["bad_open_range"] = int(bad_open_range)
    metrics["neg_prices"] = int(neg_prices)
    metrics["zero_volume"] = int(zero_volume)
    metrics["missing_open"] = int(frame["open"].isna().sum())
    metrics["missing_close"] = int(frame["close"].isna().sum())
    metrics["missing_volume"] = int(frame["volume"].isna().sum())

    if bad_high_low > 0:
        issues.append(f"high<low in {bad_high_low} rows")
    if bad_close_range > 0:
        issues.append(f"close outside high/low in {bad_close_range} rows")
    if bad_open_range > 0:
        issues.append(f"open outside high/low in {bad_open_range} rows")
    if neg_prices > 0:
        issues.append(f"{neg_prices} negative prices")
    if metrics["missing_close"] > 0:
        issues.append(f"missing close in {metrics['missing_close']} rows")

    # Date gaps (more than 5 business days = ~7 calendar days between rows)
    sorted_ts = frame["timestamp"].sort_values().reset_index(drop=True)
    gaps = sorted_ts.diff().dt.days.fillna(0)
    long_gaps = (gaps > 7).sum()
    metrics["long_gaps"] = int(long_gaps)

    # Stats
    metrics["avg_close_vnd"] = round(float(frame["close"].mean()), 2)
    metrics["min_close_vnd"] = round(float(frame["close"].min()), 2)
    metrics["max_close_vnd"] = round(float(frame["close"].max()), 2)
    metrics["avg_volume"] = round(float(frame["volume"].mean()), 2)
    metrics["total_volume"] = round(float(frame["volume"].sum()), 2)

    metrics["status"] = "ok" if not issues else "warnings"
    metrics["issues"] = issues
    return metrics


def ingest_symbol(
    provider: SSIVNProvider,
    symbol: str,
    lookback_days: int,
    skip_silver: bool,
    skip_gold: bool,
    bronze: BronzeLayer | None,
    silver: SilverLayer | None,
    gold: GoldLayer | None,
) -> dict:
    """Fetch + transform a single VN ticker."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    started = time.time()

    result: dict = {"symbol": symbol}
    try:
        frame = provider.get_historical_data(symbol, start=start, end=end, interval="1d")
    except Exception as exc:  # noqa: BLE001
        result["status"] = "fetch_failed"
        result["error"] = str(exc)
        return result

    quality = quality_report(frame, symbol)
    result["quality"] = quality

    if bronze is not None:
        try:
            bronze_meta = bronze.append(frame, lineage={"source": provider.source_name})
            bronze_records = (
                bronze_meta.get("records_written")
                if isinstance(bronze_meta, dict)
                else len(frame)
            )
            result["bronze_records"] = int(bronze_records or len(frame))
        except Exception as exc:  # noqa: BLE001
            result["bronze_error"] = str(exc)

    if not skip_silver and silver is not None:
        try:
            silver_outcome = silver.transform(frame)
            if isinstance(silver_outcome, tuple) and len(silver_outcome) == 2:
                silver_frame, silver_meta = silver_outcome
                # silver.transform() returns (clean_frame, error_frame) — write clean frame
                silver_quality = {
                    "source": provider.source_name,
                    "original_rows": int(len(frame)),
                    "clean_rows": int(len(silver_frame)),
                    "errors_rows": int(len(silver_meta)),
                }
                silver_write = silver.write(silver_frame, silver_quality)
                result["silver_records"] = int(silver_write.get("records", len(silver_frame)))
                result["silver_errors"] = int(len(silver_meta))
            else:
                result["silver_records"] = 0
                result["silver_error"] = "unexpected silver.transform() output"
        except Exception as exc:  # noqa: BLE001
            result["silver_error"] = str(exc)

    if not skip_gold and gold is not None:
        try:
            silver_frame = silver.read(symbol) if silver is not None else frame
            gold_frame = gold.transform(silver_frame)
            if gold_frame is not None and not gold_frame.empty:
                gold_meta = gold.write(gold_frame)
                if isinstance(gold_meta, dict):
                    result["gold_records"] = int(
                        gold_meta.get("records", len(gold_frame))
                    )
                else:
                    result["gold_records"] = int(len(gold_frame))
            else:
                result["gold_records"] = 0
        except Exception as exc:  # noqa: BLE001
            result["gold_error"] = str(exc)

    result["status"] = quality["status"]
    result["elapsed_s"] = round(time.time() - started, 2)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    symbols = resolve_symbols(args.symbols)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 70)
    logger.info("VIETNAMESE STOCK INGESTION (SSI iBoard)")
    logger.info("Symbols:     %d", len(symbols))
    logger.info("Lookback:    %d days (~%.1f years)", args.lookback, args.lookback / 365.25)
    logger.info("Pipeline:    bronze=%s silver=%s gold=%s",
                not args.no_pipeline,
                not args.no_pipeline and not args.skip_silver,
                not args.no_pipeline and not args.skip_gold)
    logger.info("=" * 70)

    provider = SSIVNProvider(rate_limit_sleep=0.3)

    bronze = silver = gold = None
    if not args.no_pipeline:
        if args.use_minio:
            from app.lakehouse.storage_factory import get_storage_backend
            storage = get_storage_backend()
            bronze = BronzeLayer(storage=storage)
            if not args.skip_silver:
                silver = SilverLayer(storage=storage)
            if not args.skip_gold:
                gold = GoldLayer(storage=storage)
        else:
            bronze = BronzeLayer()
            if not args.skip_silver:
                silver = SilverLayer()
            if not args.skip_gold:
                gold = GoldLayer()

    summaries: list[dict] = []
    started_all = time.time()
    for index, symbol in enumerate(symbols, start=1):
        logger.info("[%d/%d] Ingesting %s", index, len(symbols), symbol)
        result = ingest_symbol(
            provider=provider,
            symbol=symbol,
            lookback_days=args.lookback,
            skip_silver=args.skip_silver,
            skip_gold=args.skip_gold,
            bronze=bronze,
            silver=silver,
            gold=gold,
        )
        q = result.get("quality", {})
        logger.info(
            "[%d/%d] %s status=%s rows=%s span=%s..%s (%.1fy)",
            index,
            len(symbols),
            symbol,
            result.get("status"),
            q.get("rows", 0),
            q.get("first_date", "-"),
            q.get("last_date", "-"),
            q.get("span_years", 0),
        )
        if "bronze_records" in result:
            logger.info(
                "[%d/%d] bronze=%d silver=%s gold=%s",
                index,
                len(symbols),
                result.get("bronze_records", 0),
                result.get("silver_records", "-"),
                result.get("gold_records", "-"),
            )

        # Per-symbol report
        report_path = REPORT_DIR / f"{symbol}.json"
        report_path.write_text(json.dumps(result, indent=2, default=str))
        summaries.append(
            {
                "symbol": symbol,
                "status": result.get("status"),
                "rows": q.get("rows", 0),
                "span_years": q.get("span_years", 0),
                "first_date": q.get("first_date"),
                "last_date": q.get("last_date"),
                "issues": q.get("issues", []),
                "bronze_records": result.get("bronze_records"),
                "silver_records": result.get("silver_records"),
                "gold_records": result.get("gold_records"),
                "elapsed_s": result.get("elapsed_s"),
            }
        )

    elapsed_all = round(time.time() - started_all, 2)
    ok = sum(1 for s in summaries if s["status"] == "ok")
    warn = sum(1 for s in summaries if s["status"] == "warnings")
    fail = sum(1 for s in summaries if s["status"] in {"empty", "fetch_failed"})

    aggregate = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": elapsed_all,
        "lookback_days": args.lookback,
        "total_symbols": len(symbols),
        "ok": ok,
        "warnings": warn,
        "failed": fail,
        "summary": summaries,
    }
    aggregate_path = REPORT_DIR / "summary.json"
    aggregate_path.write_text(json.dumps(aggregate, indent=2, default=str))

    logger.info("=" * 70)
    logger.info("VN INGESTION COMPLETE in %.1fs", elapsed_all)
    logger.info("OK=%d  warnings=%d  failed=%d  total=%d", ok, warn, fail, len(symbols))
    logger.info("Aggregate report: %s", aggregate_path)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
