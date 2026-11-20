"""Read-only audit of every listed stock and its saved forecast families.

Only calls GET endpoints. It never ingests, trains, publishes or scores.
Saves complete responses for review and supports resuming a partial scan.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    started = datetime.now(timezone.utc).isoformat()
    clock_start = time.monotonic()

    def get(path: str) -> dict:
        before = time.monotonic()
        try:
            with urlopen(args.base_url + path, timeout=args.timeout) as response:
                payload = json.load(response)
                return {"http_status": response.status, "seconds": round(time.monotonic() - before, 3), "response": payload}
        except HTTPError as exc:
            return {"http_status": exc.code, "seconds": round(time.monotonic() - before, 3), "error": exc.read(4000).decode("utf-8", errors="replace")}
        except Exception as exc:
            return {"http_status": None, "seconds": round(time.monotonic() - before, 3), "error": f"{type(exc).__name__}: {exc}"}

    listed = get("/stocks/symbols")
    symbols = list(dict.fromkeys(listed.get("response", {}).get("data", {}).get("symbols", [])))
    if not symbols:
        raise RuntimeError(f"No symbols could be enumerated: {listed}")

    inventory: dict[str, list[str]] = {}
    for symbol in symbols:
        families = {"linear_regression"}
        for family in ("arima", "lstm"):
            if (backend / "data" / "models" / symbol / family / "registry.json").is_file():
                families.add(family)
        inventory[symbol] = sorted(families)

    results: dict[str, dict] = {}
    if args.resume and args.output.is_file():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        started = previous.get("started_at_utc", started)
        results = {r["symbol"]: r for r in previous.get("results", []) if r["symbol"] in symbols}

    def inspect(symbol: str) -> dict:
        escaped = quote(symbol, safe="")
        latest = get(f"/stocks/{escaped}/latest")
        forecasts = {}
        for family in inventory[symbol]:
            forecasts[family] = get(f"/forecast/next-session/{escaped}?" + urlencode({"model_name": family, "horizon": 1}))
        return {"symbol": symbol, "latest": latest, "forecasts": forecasts}

    def summarize() -> dict:
        latest_status = Counter()
        layer_counts = Counter()
        latest_dates = Counter()
        forecast_status: dict[str, Counter] = {}
        latency = []
        for row in results.values():
            latest = row["latest"]
            data = latest.get("response", {}).get("data", {})
            if latest.get("http_status") == 200 and data.get("close") is not None:
                latest_status["readable"] += 1
                layer_counts[data.get("source_layer", "unknown")] += 1
                latest_dates[str(data.get("timestamp", ""))[:10]] += 1
            else:
                latest_status["failed"] += 1
            latency.append(latest["seconds"])
            for family, checked in row["forecasts"].items():
                counts = forecast_status.setdefault(family, Counter())
                payload = checked.get("response", {}).get("data", {})
                if checked.get("http_status") != 200:
                    counts["http_or_transport_error"] += 1
                elif not payload.get("available"):
                    counts["unavailable"] += 1
                else:
                    counts["available"] += 1
                    value = payload.get("predicted_close")
                    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                        counts["nonpositive_or_nonfinite"] += 1
                    if (payload.get("data_staleness_days") or 0) > 0:
                        counts["stale_inputs"] += 1
                latency.append(checked["seconds"])
        latency.sort()
        return {
            "listed_symbols": len(symbols),
            "completed_symbols": len(results),
            "latest_status": dict(latest_status),
            "source_layers": dict(layer_counts),
            "latest_timestamp_dates": dict(sorted(latest_dates.items())),
            "forecast_status": {k: dict(v) for k, v in forecast_status.items()},
            "requests_checked": len(latency),
            "latency_p50_seconds": latency[len(latency) // 2] if latency else None,
            "latency_p95_seconds": latency[min(len(latency) - 1, int(len(latency) * .95))] if latency else None,
        }

    def save(complete: bool) -> None:
        report = {
            "started_at_utc": started,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_url": args.base_url,
            "workers": args.workers,
            "complete": complete,
            "scope": "All API-listed symbols: latest quote and LR forecast; additionally ARIMA/LSTM where a registry exists locally. GET only. No provider re-fetch or new ingestion.",
            "summary": summarize(),
            "results": [results[s] for s in symbols if s in results],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(args.output)

    remaining = [s for s in symbols if s not in results]
    print(json.dumps({"listed": len(symbols), "remaining": len(remaining), "planned_forecast_checks": sum(len(v) for v in inventory.values()), "output": str(args.output)}), flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(inspect, s): s for s in remaining}
        for completed in as_completed(pending):
            symbol = pending[completed]
            results[symbol] = completed.result()
            if len(results) % 25 == 0 or len(results) == len(symbols):
                save(complete=len(results) == len(symbols))
                print(json.dumps({"completed": len(results), "total": len(symbols), "elapsed_seconds": round(time.monotonic() - clock_start, 1), "summary": summarize()}), flush=True)
    save(complete=True)


if __name__ == "__main__":
    main()
