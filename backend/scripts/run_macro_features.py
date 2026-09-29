"""Compute macro and market-regime features and write to CSV/Parquet.

Example::

    python scripts/run_macro_features.py --symbol AAPL \\
        --index ^GSPC --output aapl_macro.csv
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
from app.features.macro_features import (
    MacroFeatureBuilder,
    add_correlation_features,
    add_market_regime_features,
)
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute macro + regime features.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--index", default="^GSPC",
                        help="Market index symbol for beta/correlation (default: ^GSPC).")
    parser.add_argument("--output", required=True,
                        help="Output file (.csv or .parquet).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    silver = SilverLayer()
    frame = silver.read(args.symbol.upper())
    if frame.empty:
        logger.error("No Silver data for %s. Run ingest first.", args.symbol)
        sys.exit(1)

    builder = MacroFeatureBuilder()
    enriched = builder.build(frame, macro_provider=None)
    enriched = add_market_regime_features(enriched)

    if args.index and args.index.upper() != args.symbol.upper():
        index_frame = silver.read(args.index.upper())
        if not index_frame.empty:
            index_frame = index_frame.sort_values("timestamp")
            index_frame["returns"] = index_frame["close"].pct_change()
            enriched = enriched.sort_values("timestamp")
            enriched["returns"] = enriched["close"].pct_change()
            enriched = add_correlation_features(enriched, index_frame)

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix == ".parquet":
        enriched.to_parquet(out_path, index=False)
    else:
        enriched.to_csv(out_path, index=False)

    print()
    print("=" * 60)
    print(f"Symbol:    {args.symbol.upper()}")
    print(f"Rows:      {len(enriched)}")
    print(f"Output:    {out_path}")
    new_cols = [c for c in enriched.columns if c not in frame.columns]
    print(f"New cols:  {new_cols}")
    print("=" * 60)


if __name__ == "__main__":
    main()