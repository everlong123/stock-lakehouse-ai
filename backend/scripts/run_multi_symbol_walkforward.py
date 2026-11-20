"""Multi-symbol walk-forward validation with a buy-and-hold benchmark.

WHY THIS SCRIPT EXISTS
----------------------
The walk-forward validator had only ever been run on ONE symbol (AAPL).
That is not enough to say anything about a trading strategy, because a
single stock over a single decade mostly measures whether that stock
went up. A thesis defence on "does this strategy work?" cannot be
answered with one symbol.

This script runs the SAME walk-forward machinery across a sample of the
universe and reports the DISTRIBUTION of the outcomes:

- median / mean Sharpe across symbols
- percentage of symbols that were profitable out of sample
- the same numbers for a buy-and-hold baseline, so the strategy is
  measured against something, not against nothing
- a breakdown by exchange, because a result that only holds on one
  market is not a general finding

WHERE THE COMPUTATION LIVES
---------------------------
NOT here. The whole computation is in
``app/services/walk_forward_report_service.py``, because the cron job
that now runs this report every day needs the SAME code. Two copies of
the aggregation logic would drift apart, and the report on the page
would stop matching the report in the log. This script is the manual
entry point; the service is the shared core.

WHERE THE RESULT GOES
---------------------
Into the lakehouse's ``backtests`` layer, so the API reads the same
object whether the report was produced by this script or by the nightly
cron job. A local copy is written next to it for convenience.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/run_multi_symbol_walkforward.py
    .venv/Scripts/python.exe scripts/run_multi_symbol_walkforward.py --limit 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import get_logger, setup_logging  # noqa: E402
from app.services.walk_forward_report_service import (  # noqa: E402
    LOCAL_REPORT_FILES,
    format_summary,
    persist_report,
    run_report,
)

logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Sample N symbols from the whole universe")
    parser.add_argument(
        "--per-exchange",
        type=int,
        default=8,
        help="Take up to N symbols from EVERY exchange (0 = use --limit only)",
    )
    parser.add_argument("--strategy", type=str, default="ma_crossover", help="Strategy name")
    parser.add_argument("--train-days", type=int, default=365, help="Train window length in days")
    parser.add_argument("--test-days", type=int, default=90, help="Test window length in days")
    parser.add_argument("--step-days", type=int, default=90, help="How far each window slides")
    parser.add_argument("--initial-capital", type=float, default=10_000.0)
    parser.add_argument("--transaction-fee", type=float, default=0.001)
    parser.add_argument("--slippage", type=float, default=0.0005)
    args = parser.parse_args(argv)

    setup_logging()

    payload = run_report(
        strategy=args.strategy,
        per_exchange=args.per_exchange,
        limit=args.limit,
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        initial_capital=args.initial_capital,
        transaction_fee=args.transaction_fee,
        slippage=args.slippage,
        progress=print,
    )

    persist_report(args.strategy, payload)

    print()
    print(format_summary(payload))
    print(f"  report : {LOCAL_REPORT_FILES.get(args.strategy, '(lakehouse backtests layer)')}")
    print("=" * 78)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
