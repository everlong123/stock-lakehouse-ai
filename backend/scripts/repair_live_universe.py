"""Rebuild derived Gold and independently evaluate current saved models.

Raw Bronze is preserved. Old model directories are archived by the trainer.
Symbols with obsolete data or inconsistent scales are reported, not fabricated.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, as_completed, wait
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def repair_one(task: tuple[str, str, str, int]) -> dict:
    phase, symbol, model_name, history_sessions = task
    logging.getLogger().setLevel(logging.ERROR)
    try:
        import pandas as pd
        from app.lakehouse.storage_factory import get_storage_backend

        storage = get_storage_backend()
        if storage.backend_name != "minio":
            raise RuntimeError("Live repair requires MinIO; refusing to use a local fallback.")
        if phase == "gold":
            from app.lakehouse.gold import GoldLayer
            from app.lakehouse.silver import SilverLayer

            logging.getLogger().setLevel(logging.ERROR)
            silver = SilverLayer(storage=storage).read(symbol)
            if silver.empty:
                return {"symbol": symbol, "phase": phase, "status": "skipped", "reason": "No Silver data"}
            gold = GoldLayer(storage=storage)
            frame = gold.transform(silver)
            gold.write(frame)
            return {"symbol": symbol, "phase": phase, "status": "repaired", "rows": len(frame)}

        from app.forecasting.trainer import train_model
        from app.lakehouse.gold import GoldLayer

        logging.getLogger().setLevel(logging.ERROR)
        frame = GoldLayer(storage=storage).read(symbol)
        minimum = 100 if model_name == "linear_regression" else 300
        if frame.empty or len(frame) < minimum:
            return {"symbol": symbol, "model": model_name, "phase": phase, "status": "skipped", "reason": f"Fewer than {minimum} historical rows"}
        newest = pd.to_datetime(frame["timestamp"], utc=True).max()
        age = (datetime.now(timezone.utc).date() - newest.date()).days
        if age > 10:
            return {"symbol": symbol, "model": model_name, "phase": phase, "status": "skipped", "reason": f"Historical listing: latest data {newest.date()}, {age} calendar days old"}
        parameters = {"epochs": 8} if model_name == "lstm" else {}
        if history_sessions:
            parameters["history_sessions"] = history_sessions
        result = train_model(symbol, model_name, full_fit=True, extra_params=parameters)
        return {"symbol": symbol, "model": model_name, "phase": phase, "status": "repaired", "model_version": result["model_version"], "mae": result["mae"], "test_points": result["test_points"]}
    except Exception as exc:
        return {"symbol": symbol, "model": model_name, "phase": phase, "status": "failed", "reason": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["gold", "models"], required=True)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--model", default="linear_regression")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--history-sessions", type=int, default=0, help="Explicit, recorded recent training window; scale guards still apply.")
    parser.add_argument("--follow-gold-report", type=Path, help="Train each symbol only after the concurrent Gold repair finished it.")
    args = parser.parse_args()
    # A rebuild must not race a refresh writer on the same partitions.
    wait_started = time.monotonic()
    while True:
        with urlopen("http://127.0.0.1:8000/api/v1/admin/auto-refresh/status", timeout=15) as response:
            running = json.load(response).get("data", {}).get("running", False)
        if not running:
            break
        if time.monotonic() - wait_started > 1800:
            raise RuntimeError("The active refresh did not finish; no repair writes were started.")
        print(json.dumps({"waiting_for_refresh": True, "elapsed": round(time.monotonic() - wait_started)}), flush=True)
        time.sleep(15)
    if args.symbols:
        symbols = list(dict.fromkeys(s.strip().upper() for s in args.symbols.split(",") if s.strip()))
    else:
        with urlopen("http://127.0.0.1:8000/api/v1/stocks/symbols", timeout=30) as response:
            symbols = list(dict.fromkeys(json.load(response)["data"]["symbols"]))
    results = []
    if args.resume and args.output.exists():
        results = json.loads(args.output.read_text(encoding="utf-8")).get("results", [])
    complete = {r["symbol"] for r in results if r["status"] in ("repaired", "skipped")}
    tasks = [(args.phase, symbol, args.model, args.history_sessions) for symbol in symbols if symbol not in complete]
    started = time.monotonic()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        report = {"phase": args.phase, "model": args.model, "updated_at_utc": datetime.now(timezone.utc).isoformat(), "total": len(symbols), "results": results}
        temp = args.output.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(args.output)

    print(json.dumps({"phase": args.phase, "tasks": len(tasks), "model": args.model}), flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        remaining = {task[1]: task for task in tasks}
        pending = {}
        while remaining or pending:
            ready = set(remaining)
            if args.follow_gold_report:
                try:
                    upstream = json.loads(args.follow_gold_report.read_text(encoding="utf-8"))
                except (FileNotFoundError, json.JSONDecodeError):
                    upstream = {"results": []}
                ready = {r["symbol"] for r in upstream["results"] if r["status"] == "repaired"}
                if len(upstream["results"]) >= upstream.get("total", float("inf")):
                    for symbol in list(remaining):
                        if symbol not in ready:
                            remaining.pop(symbol)
                            results.append({"symbol": symbol, "phase": args.phase, "status": "skipped", "reason": "Gold could not be rebuilt"})
            for symbol in list(remaining):
                if len(pending) >= args.workers * 2:
                    break
                if symbol in ready:
                    future = pool.submit(repair_one, remaining.pop(symbol))
                    pending[future] = symbol
            if not pending:
                if remaining:
                    time.sleep(3)
                continue
            finished, _ = wait(pending, timeout=3, return_when=FIRST_COMPLETED)
            for future in finished:
                pending.pop(future)
                result = future.result()
                results.append(result)
                if len(results) % 20 == 0 or result["status"] == "failed":
                    save()
                    print(json.dumps({"done": len(results), "total": len(symbols), "elapsed": round(time.monotonic() - started, 1), "latest": result}), flush=True)
    save()
    from collections import Counter

    print(json.dumps({"status": dict(Counter(r["status"] for r in results)), "report": str(args.output)}), flush=True)


if __name__ == "__main__":
    main()
