"""Entrypoint for the cron jobs.

WHY A SCRIPT AND NOT THE `schedule` LIBRARY
--------------------------------------------
The project used to run its batch through ``scripts/schedule_batch.py``,
which uses the ``schedule`` package inside a standalone Python process. That
process dies with the machine, and it is not supervised by Docker: if the
container is recreated, the schedule is gone.

A real cron inside a container is supervised by the container runtime: the
``scheduler`` service in ``docker-compose.yml`` runs ``cron -f``, and
``backend/crontab`` holds the timetable. The container restarts with
``restart: unless-stopped``, so the timetable survives a crash and a
reboot.

WHAT THIS SCRIPT DOES
---------------------
It is the entrypoint cron calls. It takes a job name and runs exactly that
job, writing a dated log so a run can be audited afterwards:

    python scripts/run_scheduled_job.py eod

THE JOBS
--------
``eod``
    The end-of-day batch: refresh the price layers for every symbol, then
    produce the next-session forecast for the symbols that have a trained
    model. This is the "closed the market, what happens next" pass.

``universe-forecast``
    Forecast the next session for EVERY symbol that has a trained model,
    then score the older forecasts against the closes that have since
    happened. This is the pass that closes the loop: it publishes the
    prediction and, a day later, checks whether it was right.

``quality-gate``
    Run the data quality gate: check that the layers agree with each
    other, that the stored rows still obey the market's rules, that the
    symbols are current, and that a slice of the universe still matches
    the live provider. This is the pass that answers "is the data we are
    serving actually right?".
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.logging_config import get_logger, setup_logging  # noqa: E402

logger = get_logger(__name__)

LOG_DIR = ROOT / "logs"
SCHEDULED_LOG = LOG_DIR / "scheduled_jobs.log"


def _log_line(message: str) -> None:
    """Append a dated line to the scheduled-job log.

    The file is the ONLY record of what cron ran. Container stdout is
    rotated away by Docker, and `docker compose logs` is not a place to look
    three weeks later when asking "did last night's batch run?".
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat()
        with SCHEDULED_LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
    except Exception:  # noqa: BLE001 - logging must never break the job
        pass


def run_eod(args: argparse.Namespace) -> dict:
    """The end-of-day batch: refresh the price layers, then forecast."""
    from app.services.auto_refresh import AutoRefreshService

    service = AutoRefreshService()
    summary = service.run_once()
    _log_line(
        f"eod: symbols={summary.get('symbols_total')} "
        f"silver={summary.get('silver_rebuilt')} gold={summary.get('gold_rebuilt')} "
        f"forecasts={summary.get('next_session_forecasts')} "
        f"errors={len(summary.get('errors') or [])}"
    )
    return summary


def run_universe_forecast(args: argparse.Namespace) -> dict:
    """Forecast the next session for EVERY symbol, then score the old ones.

    WHY A SEPARATE JOB AND NOT PART OF ``eod``
    -------------------------------------------
    The EOD batch refreshes the price layers for ~950 symbols, and it does
    so while people are using the site. The universe forecast has to TRAIN
    the symbols whose models have gone stale, and a training pass over the
    whole universe takes minutes. Folding that into the refresh pass would
    make the refresh much longer and harder to reason about.

    Splitting them keeps each job with one job:
      * ``eod``                 - make the data current,
      * ``universe-forecast``   - predict from it, then verify the past.

    The two are scheduled a few hours apart, so the forecast runs on data
    that is already settled.
    """
    from app.services.universe_forecast import run_universe_forecast as _run

    # `--model` accepts a comma-separated list so the batch can publish
    # one forecast per model for the same target session.
    models = [name.strip() for name in str(args.model).split(",") if name.strip()]
    if not models:
        models = ["linear_regression"]

    summary = _run(
        model_name=models if len(models) > 1 else models[0],
        train=not args.no_train,
    )
    payload = summary.as_dict()
    _log_line(
        f"universe-forecast: models={','.join(models)} "
        f"trained={payload['trained']} forecasts={payload['forecast']} "
        f"stored={payload['stored']} scored={payload['scored']} "
        f"errors={len(payload['errors'])} elapsed={payload['elapsed_seconds']}s"
    )
    return payload


def run_quality_gate(args: argparse.Namespace) -> dict:
    """Run the data quality gate and store its verdict.

    WHY THIS IS A SEPARATE JOB
    --------------------------
    The gate is the only pass that asks "is the data we are serving
    correct?". It is also the only pass that makes a NETWORK CALL to the
    provider, so it must not be folded into the EOD batch: a provider
    outage would then stall the price refresh instead of only the
    verification.

    The provider comparison runs on a ROTATION - each pass checks a slice
    of the universe and remembers where it stopped - so a full sweep
    completes over several passes while each individual pass stays short
    enough to fit between the EOD runs.
    """
    from app.services.quality_gate_service import run_and_persist

    payload = run_and_persist(provider_name=args.provider)
    _log_line(
        f"quality-gate: verdict={payload.get('verdict')} "
        f"batch={payload.get('provider_batch_size')} "
        f"elapsed={payload.get('elapsed_seconds')}s"
    )
    return payload


JOBS = {
    "eod": run_eod,
    "universe-forecast": run_universe_forecast,
    "quality-gate": run_quality_gate,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "job",
        choices=sorted(JOBS),
        help="The job to run: eod, universe-forecast, quality-gate",
    )
    parser.add_argument(
        "--model",
        default="linear_regression",
        help=(
            "The model(s) the universe forecast uses. Comma-separated to "
            "publish one forecast per model for the same session, e.g. "
            "'linear_regression,arima,lstm'. A symbol without a trained "
            "model for one of them gets no row for that model."
        ),
    )
    parser.add_argument(
        "--provider",
        default="yahoo_http",
        help="The provider the quality gate re-fetches from.",
    )
    parser.add_argument(
        "--no-train",
        action="store_true",
        help="Skip the training pass; use the models that are already on disk.",
    )
    args = parser.parse_args(argv)

    setup_logging()
    started = datetime.now(timezone.utc)
    _log_line(f"start job={args.job}")

    try:
        result = JOBS[args.job](args)
    except Exception as exc:  # noqa: BLE001
        # A failing job must not take cron down. cron keeps running the
        # timetable regardless, and the log line records the failure.
        logger.exception("Scheduled job %s failed", args.job)
        _log_line(f"fail job={args.job} error={exc}")
        print(json.dumps({"job": args.job, "ok": False, "error": str(exc)}))
        traceback.print_exc()
        return 1

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    _log_line(f"done job={args.job} elapsed={elapsed:.1f}s")
    print(json.dumps({"job": args.job, "ok": True, "elapsed_seconds": elapsed, "result": result}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
