"""Walk-forward validation CLI - chạy backtesting trên rolling windows.

Ví dụ::

    python scripts/run_walk_forward.py --symbol AAPL --strategy ma_crossover
    python scripts/run_walk_forward.py --symbol MSFT --strategy rsi --windows 8

Dùng Gold layer làm input, kết quả in ra terminal + lưu JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtesting.walk_forward import WalkForwardValidator
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-forward backtest runner.")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--strategy", default="ma_crossover",
                        choices=["ma_crossover", "rsi"])
    parser.add_argument("--initial-capital", type=float, default=10_000.0)
    parser.add_argument("--fee", type=float, default=0.001,
                        help="Transaction fee as a fraction (default: 0.001 = 0.1%).")
    parser.add_argument("--slippage", type=float, default=0.0005,
                        help="Slippage as a fraction (default: 0.05%).")
    parser.add_argument("--out", default=None,
                        help="Optional path to dump the JSON report.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    validator = WalkForwardValidator()
    result = validator.run(
        symbol=args.symbol.upper(),
        strategy_name=args.strategy,
        initial_capital=args.initial_capital,
        transaction_fee=args.fee,
        slippage=args.slippage,
    )

    print()
    print("=" * 60)
    print(f"Walk-Forward Validation - {args.symbol.upper()} / {args.strategy}")
    print("=" * 60)
    print(json.dumps(result, default=str, indent=2))
    print("=" * 60)

    if args.out:
        Path(args.out).write_text(json.dumps(result, default=str, indent=2), encoding="utf-8")
        logger.info("Wrote JSON report to %s", args.out)


if __name__ == "__main__":
    main()