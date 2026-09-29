"""Compute technical indicators from Silver layer to a CSV/Parquet output.

Useful for ad-hoc analysis outside the Gold layer pipeline::

    python scripts/run_indicators.py --symbol AAPL --output indicators_aapl.csv
    python scripts/run_indicators.py --symbol MSFT --rsi 21 --sma 5,10,20,50,200 \\
        --output msft_features.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from app.core.logging_config import get_logger
from app.indicators.service import IndicatorConfig, add_indicators
from app.lakehouse.silver import SilverLayer

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute indicators from Silver layer.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--sma", default="5,10,20,50",
                        help="Comma-separated SMA windows (default: 5,10,20,50).")
    parser.add_argument("--ema", default="12,26",
                        help="Comma-separated EMA windows (default: 12,26).")
    parser.add_argument("--rsi", type=int, default=14)
    parser.add_argument("--bb-window", type=int, default=20)
    parser.add_argument("--bb-std", type=float, default=2.0)
    parser.add_argument("--macd-fast", type=int, default=12)
    parser.add_argument("--macd-slow", type=int, default=26)
    parser.add_argument("--macd-signal", type=int, default=9)
    parser.add_argument("--output", required=True,
                        help="Where to write the output (.csv or .parquet).")
    return parser.parse_args(argv)


def _parse_ints(raw: str) -> tuple[int, ...]:
    return tuple(int(item.strip()) for item in raw.split(",") if item.strip())


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    silver = SilverLayer()
    frame = silver.read(args.symbol.upper())
    if frame.empty:
        logger.error("No Silver data for %s. Run ingest first.", args.symbol)
        sys.exit(1)

    config = IndicatorConfig(
        sma_windows=_parse_ints(args.sma),
        ema_windows=_parse_ints(args.ema),
        rsi_period=args.rsi,
        bb_window=args.bb_window,
        bb_std=args.bb_std,
        macd_fast=args.macd_fast,
        macd_slow=args.macd_slow,
        macd_signal=args.macd_signal,
    )
    enriched = add_indicators(frame, config=config)

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix == ".parquet":
        enriched.to_parquet(out_path, index=False)
    else:
        enriched.to_csv(out_path, index=False)

    print()
    print("=" * 60)
    print(f"Symbol:   {args.symbol.upper()}")
    print(f"Rows:     {len(enriched)}")
    print(f"Features: {[c for c in enriched.columns if c not in frame.columns]}")
    print(f"Output:   {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()