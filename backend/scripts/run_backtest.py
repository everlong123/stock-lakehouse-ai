"""CLI entry-point for running a backtest against Gold layer data.

Examples::

    python scripts/run_backtest.py --symbol AAPL --strategy ma_crossover
    python scripts/run_backtest.py --symbol MSFT --strategy rsi --capital 50000
    python scripts/run_backtest.py --symbol NVDA --strategy ma_crossover \\
        --start 2022-01-01 --end 2025-12-31
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtesting.engine import BacktestEngine
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single-symbol backtest.")
    parser.add_argument("--symbol", required=True, help="Ticker symbol (e.g. AAPL)")
    parser.add_argument("--strategy", default="ma_crossover",
                        choices=["ma_crossover", "rsi"])
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--fee", type=float, default=0.001,
                        help="Transaction fee (default: 0.001 = 0.1%).")
    parser.add_argument("--slippage", type=float, default=0.0005,
                        help="Slippage (default: 0.05%).")
    parser.add_argument("--out", default=None, help="Write JSON result to this path.")
    parser.add_argument("--params", default=None,
                        help="JSON-encoded strategy params override.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    params = json.loads(args.params) if args.params else None

    engine = BacktestEngine()
    result = engine.run(
        symbol=args.symbol.upper(),
        strategy_name=args.strategy,
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        transaction_fee=args.fee,
        slippage=args.slippage,
        parameters=params,
    )

    print()
    print("=" * 60)
    print(f"Backtest - {result['symbol']} / {result['strategy']}")
    print("=" * 60)
    print(f"Period:            {result['start_date']} -> {result['end_date']}")
    print(f"Initial capital:   {result['initial_capital']:.2f}")
    print(f"Final capital:     {result['final_capital']:.2f}")
    print(f"Total return:      {result['total_return'] * 100:.2f}%")
    print(f"Win rate:          {result['win_rate'] * 100:.2f}%")
    print(f"Sharpe ratio:      {result['sharpe_ratio']:.3f}")
    print(f"Max drawdown:      {result['maximum_drawdown'] * 100:.2f}%")
    print(f"Number of trades:  {result['number_of_trades']}")
    print("=" * 60)

    if args.out:
        Path(args.out).write_text(json.dumps(result, default=str, indent=2), encoding="utf-8")
        logger.info("Wrote backtest JSON to %s", args.out)


if __name__ == "__main__":
    main()