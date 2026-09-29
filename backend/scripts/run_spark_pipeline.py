"""Run the Spark-based Medallion transformation end-to-end.

This script is invoked when ``USE_SPARK=true`` (or ``--use-spark`` is passed
on the CLI).  It reads raw Parquet from the **Bronze** layer with PySpark,
applies the same cleaning rules as the Pandas implementation, then writes
the result back to the **Silver** layer using Spark's Parquet writer.

It exists separately from :mod:`app.lakehouse.pipeline` because Spark jobs
benefit from explicit entry points - they can be submitted via
``spark-submit`` and their lifecycle is easier to reason about when they
don't share memory with the FastAPI process.

Usage::

    # From within the backend venv (PySpark installed locally)
    python scripts/run_spark_pipeline.py --symbols AAPL,MSFT --interval 1d

    # From docker-compose jupyter container
    docker compose exec jupyter python /workspace/scripts/run_spark_pipeline.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.constants import OHLCV_COLUMNS
from app.core.logging_config import get_logger
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.spark_session import get_spark_session
from app.lakehouse.storage_base import StorageBackend
from app.lakehouse.storage_factory import get_storage_backend

logger = get_logger(__name__)


def _to_spark(spark, frame):
    """Cast a Pandas frame to a typed Spark DataFrame."""

    from pyspark.sql import functions as F
    from pyspark.sql.types import DoubleType, StringType, TimestampType

    sdf = spark.createDataFrame(frame)
    sdf = sdf.withColumn("symbol", F.upper(F.col("symbol").cast(StringType())))
    sdf = sdf.withColumn(
        "timestamp", F.to_utc_timestamp(F.col("timestamp").cast(TimestampType()), "UTC")
    )
    sdf = sdf.withColumn("ingestion_time", F.col("ingestion_time").cast(TimestampType()))
    for col in ["open", "high", "low", "close", "adj_close", "volume"]:
        sdf = sdf.withColumn(col, F.col(col).cast(DoubleType()))
    return sdf


def _clean_spark(sdf):
    """Apply Silver cleaning rules."""

    from pyspark.sql import functions as F

    invalid = (
        F.col("open").isNull()
        | F.col("high").isNull()
        | F.col("low").isNull()
        | F.col("close").isNull()
        | F.col("volume").isNull()
        | (F.col("high") < F.col("open"))
        | (F.col("high") < F.col("close"))
        | (F.col("low") > F.col("open"))
        | (F.col("low") > F.col("close"))
        | (F.col("high") < F.col("low"))
        | (F.col("volume") < 0)
    )
    return (
        sdf.filter(~invalid)
        .dropDuplicates(["symbol", "timestamp"])
        .orderBy("symbol", "timestamp")
    )


def run_spark_pipeline(symbols: list[str], storage: StorageBackend) -> dict[str, dict[str, int]]:
    spark = get_spark_session()
    if spark is None:
        raise RuntimeError(
            "Spark is not available. Set USE_SPARK=true in .env or pass --use-spark."
        )

    bronze = BronzeLayer(storage=storage)
    summary: dict[str, dict[str, int]] = {}

    for symbol in symbols:
        start = time.time()
        frame = bronze.read(symbol)
        if frame.empty:
            logger.warning("No Bronze data for %s", symbol)
            summary[symbol] = {"bronze": 0, "silver": 0}
            continue

        sdf = _to_spark(spark, frame)
        silver_sdf = _clean_spark(sdf)
        silver_pd = silver_sdf.toPandas()

        relative_path = (
            f"symbol={symbol.upper()}/year={silver_pd['timestamp'].dt.year.max()}/"
            f"month={silver_pd['timestamp'].dt.month.max():02d}/data.parquet"
        )
        path = storage.write_parquet("silver", relative_path, silver_pd[OHLCV_COLUMNS])
        logger.info(
            "Spark Silver write %s: %d rows -> %s (%.1fs)",
            symbol,
            len(silver_pd),
            path,
            time.time() - start,
        )
        summary[symbol] = {"bronze": len(frame), "silver": len(silver_pd)}

    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PySpark Silver/Gold pipeline runner.")
    parser.add_argument("--symbols", default="AAPL,MSFT,GOOGL",
                        help="Comma-separated tickers (default: AAPL,MSFT,GOOGL).")
    parser.add_argument("--use-spark", action="store_true",
                        help="Force USE_SPARK=true for this run.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.use_spark:
        from app.core import config as cfg

        cfg.settings.use_spark = True

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    storage = get_storage_backend()
    summary = run_spark_pipeline(symbols, storage)

    logger.info("=" * 60)
    logger.info("Spark pipeline summary:")
    for symbol, counts in summary.items():
        logger.info("  %s -> bronze=%d silver=%d", symbol, counts["bronze"], counts["silver"])
    logger.info("=" * 60)


if __name__ == "__main__":
    main()