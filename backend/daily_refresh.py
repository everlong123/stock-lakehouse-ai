"""Daily scheduled refresh — push yesterday + today data into MinIO.

Run by Windows Task Scheduler at the configured time (default 18:00 local).
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
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

import requests

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")


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
            print(f"  poll error: {exc}", file=sys.stderr)
        time.sleep(15)

    return {"error": "timeout", "last_summary": {}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        default=os.getenv("REFRESH_SYMBOLS", ""),
        help="comma-separated symbols; empty = use all configured",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None
    print(f"[{datetime.now().isoformat()}] starting daily refresh", symbols or "ALL")

    try:
        result = trigger_run(symbols)
        print(f"  queued: {result}")
    except Exception as exc:
        print(f"  trigger failed: {exc}", file=sys.stderr)
        return 1

    print("  waiting for completion...")
    summary = wait_for_finish(timeout_seconds=1800)
    print(f"  done: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
