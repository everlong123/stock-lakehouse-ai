"""Publish one forecast per model for a list of symbols.

WHY THIS SCRIPT EXISTS
----------------------
The nightly batch (`scripts/run_scheduled_job.py universe-forecast`) can
already publish one forecast per model - it accepts a comma-separated
`--model` list. This script does the same thing for an EXPLICIT list of
symbols, which is what a researcher needs after training a set of
representative tickers: "run the forecast for exactly these symbols,
with these three models, and write the rows".

It is a thin wrapper on purpose. The forecast, the store and the score
all live in `app/services/universe_forecast.py`, so this script cannot
drift away from what the nightly batch does.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.logging_config import setup_logging  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols",
        default="",
        help="Comma-separated symbols. Empty means every symbol in Gold.",
    )
    parser.add_argument(
        "--models",
        default="linear_regression,arima,lstm",
        help="Comma-separated model families.",
    )
    parser.add_argument(
        "--no-train",
        action="store_true",
        help="Skip the training pass; use the models already on disk.",
    )
    parser.add_argument("--output", type=Path, help="Save the complete publication/scoring summary as JSON.")
    args = parser.parse_args()

    setup_logging()
    from app.services.universe_forecast import run_universe_forecast

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    models = [m.strip().lower() for m in args.models.split(",") if m.strip()]

    started = time.perf_counter()
    summary = run_universe_forecast(
        symbols=symbols or None,
        model_name=models,
        train=not args.no_train,
    )
    payload = summary.as_dict()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"[publish-forecasts] models={','.join(models)} "
        f"symbols={len(symbols) or 'all'} "
        f"forecasts={payload['forecast']} stored={payload['stored']} "
        f"scored={payload['scored']} failed={payload['forecast_failed']} "
        f"elapsed={payload['elapsed_seconds']}s",
        flush=True,
    )
    for error in payload["errors"][:10]:
        print(f"  {error}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
