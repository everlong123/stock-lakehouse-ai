"""Train the universe model for every symbol in the Gold layer.

WHY THIS SCRIPT EXISTS
----------------------
The forecasting system used to cover 18 hand-picked symbols. This script
covers the WHOLE lakehouse. It is the one-off bootstrap: once every
symbol has a model, the nightly ``universe-forecast`` job only has to
retrain the symbols whose model has gone stale.

The run is resumable: ``--force`` retrains everything, and without it the
symbols that already have a fresh model are skipped.

ROLLING REFIT
-------------
``--end-date`` trains on the sessions up to (and including) that date only.
The chronological split is then carved out of that truncated history, so the
hold-out the model is scored on contains sessions the model has never seen.
This is the walk-forward shape: run the script once per session with
``--end-date <that session>`` and you get an honest, sequential evaluation
of a model that is retrained every night.

    python scripts/train_universe.py --model linear_regression
    python scripts/train_universe.py --model arima --end-date 2026-11-10
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.logging_config import get_logger, setup_logging  # noqa: E402

logger = get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="linear_regression")
    parser.add_argument("--force", action="store_true", help="Retrain every symbol.")
    parser.add_argument("--limit", type=int, default=0, help="Only the first N symbols.")
    parser.add_argument(
        "--end-date",
        default="",
        help=(
            "Rolling refit: train only on sessions at or before this date "
            "(YYYY-MM-DD). The hold-out is then genuinely unseen data."
        ),
    )
    parser.add_argument(
        "--full-fit",
        action="store_true",
        help=(
            "Ship the model fitted on 100%% of the (truncated) history, while "
            "still reporting the hold-out metrics from the 60/20/20 split."
        ),
    )
    args = parser.parse_args()

    setup_logging()

    from app.forecasting.universe_training import list_gold_symbols, train_universe

    end_date = args.end_date.strip() or None
    if end_date is not None:
        import pandas as pd

        parsed = pd.to_datetime(end_date, errors="coerce", utc=True)
        if pd.isna(parsed):
            print(f"[universe-training] --end-date {end_date!r} is not a valid date")
            return 2
        end_date = parsed

    symbols = list_gold_symbols()
    if args.limit:
        symbols = symbols[: args.limit]
    print(
        f"[universe-training] {len(symbols)} symbols, model={args.model}"
        + (f", end_date={end_date}" if end_date else "")
        + (", full_fit=True" if args.full_fit else "")
    )

    started = time.perf_counter()
    last_report = started

    def progress(index: int, total: int, symbol: str) -> None:
        nonlocal last_report
        now = time.perf_counter()
        if now - last_report < 10 and index != total:
            return
        last_report = now
        elapsed = now - started
        rate = index / elapsed if elapsed else 0
        remaining = (total - index) / rate if rate else 0
        print(
            f"[universe-training] {index}/{total} {symbol} "
            f"elapsed={elapsed:.0f}s eta={remaining:.0f}s",
            flush=True,
        )

    summary = train_universe(
        symbols=symbols,
        model_name=args.model,
        force=args.force,
        progress=progress,
        end_date=end_date,
        full_fit=args.full_fit,
    )
    payload = summary.as_dict()
    print(f"[universe-training] done: {payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
