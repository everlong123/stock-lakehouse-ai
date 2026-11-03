"""Daily scheduled refresh — push yesterday + today data into MinIO.

Run by Windows Task Scheduler at the configured time (default 06:00 local).
Calls /api/v1/admin/auto-refresh/run, which queues the run in the background
on the backend.

Idempotent: the auto-refresh service only fetches from (max_timestamp + 1 day),
so multiple runs the same day produce no duplicate rows.

Usage:
  python daily_refresh.py
  python daily_refresh.py --symbols AAPL,MSFT,GOOGL

Environment:
  API_BASE       (default http://127.0.0.1:8000)
  REFRESH_SYMBOLS  (default = all configured symbols)
  WAIT_FOR_BACKEND_SECONDS  (default 3600) - how long to wait for the API to
                    come up before giving up. The scheduled task fires at
                    06:00, when nothing is running yet, so the first
                    attempts always fail with a connection error. One hour
                    covers "the user opened the laptop and started the stack
                    some time after 06:00".
  LOG_FILE       (default logs/daily_refresh.log) - this script runs under
                    `pythonw.exe` with the window hidden, so stdout goes
                    nowhere. Without a log file a failed run is completely
                    silent.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
WAIT_FOR_BACKEND_SECONDS = int(os.getenv("WAIT_FOR_BACKEND_SECONDS", "3600"))
BACKEND_ROOT = Path(__file__).resolve().parent
LOG_FILE = Path(
    os.getenv("LOG_FILE", str(BACKEND_ROOT / "logs" / "daily_refresh.log"))
)


def _log(message: str) -> None:
    """Write to the log file and, when attached to a console, to stdout."""
    line = f"[{datetime.now().isoformat()}] {message}"
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass
    if sys.stdout is not None:
        try:
            print(line, flush=True)
        except Exception:  # noqa: BLE001 - stdout may be None under pythonw
            pass


def wait_for_backend(timeout_seconds: int = WAIT_FOR_BACKEND_SECONDS) -> bool:
    """Poll the health endpoint until the API answers or the timeout expires.

    The scheduled task fires at 06:00 while the dev stack is still down, so
    without this the run fails instantly with a connection refused error and
    the day is silently missed. The backend is started by hand later, so we
    wait for it.
    """
    url = f"{API_BASE}/api/v1/health"
    deadline = time.time() + timeout_seconds
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            r = requests.get(url, timeout=5)
            if r.ok:
                _log(f"backend is up after {attempt} attempt(s)")
                return True
            _log(f"backend not ready yet (HTTP {r.status_code}), attempt {attempt}")
        except Exception as exc:  # noqa: BLE001 - any transport error means "not up"
            _log(f"backend not reachable yet: {exc}, attempt {attempt}")
        time.sleep(15)
    return False


def trigger_run(symbols: list[str] | None) -> dict:
    url = f"{API_BASE}/api/v1/admin/auto-refresh/run"
    params = {}
    if symbols:
        params["symbols"] = ",".join(symbols)
    r = requests.post(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def wait_for_finish(timeout_seconds: int = 1800) -> dict:
    """Poll /admin/auto-refresh/status until last_run_at >= started_at."""
    started = datetime.utcnow()
    url = f"{API_BASE}/api/v1/admin/auto-refresh/status"
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json().get("data") or {}
            last_run = data.get("last_run_at")
            if last_run:
                # Parse ISO and compare
                last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                if last_dt.replace(tzinfo=None) >= started:
                    return data
        except Exception as exc:
            _log(f"poll error: {exc}")
        time.sleep(15)

    return {"error": "timeout", "last_summary": {}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        default=os.getenv("REFRESH_SYMBOLS", ""),
        help="comma-separated symbols; empty = use all configured",
    )
    parser.add_argument(
        "--wait-for-backend",
        type=int,
        default=WAIT_FOR_BACKEND_SECONDS,
        help="seconds to wait for the API to come up (0 = do not wait)",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None
    _log(f"starting daily refresh {symbols or 'ALL'}")

    if args.wait_for_backend > 0:
        if not wait_for_backend(args.wait_for_backend):
            _log("backend never became available - aborting")
            return 1

    try:
        result = trigger_run(symbols)
        _log(f"queued: {result}")
    except Exception as exc:
        _log(f"trigger failed: {exc}")
        return 1

    _log("waiting for completion...")
    summary = wait_for_finish(timeout_seconds=1800)
    _log(f"done: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
