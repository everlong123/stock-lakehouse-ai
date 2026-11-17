"""Backfill the verification ledger with the system's historical predictions.

WHY THIS SCRIPT EXISTS
----------------------
The verification ledger fills itself one row per day from now on. This
script fills it with the model's OWN past predictions, replayed over the
historical hold-out split, so the accuracy report has enough rows to be a
measurement rather than an anecdote.

Every backfilled row is tagged ``backfill_walk_forward`` and is reported
separately from the rows the nightly batch actually published.

    python scripts/backfill_forecast_ledger.py --model linear_regression
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.logging_config import setup_logging  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="linear_regression")
    parser.add_argument("--limit", type=int, default=60, help="Sessions per symbol.")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols.")
    args = parser.parse_args()

    setup_logging()

    from app.services.forecast_backfill import backfill_universe

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None
    summary = backfill_universe(symbols=symbols, model_name=args.model, limit=args.limit)
    print(f"[backfill] {summary.as_dict()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
