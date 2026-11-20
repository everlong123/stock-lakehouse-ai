"""Audit real API histories, both backtests and offline agent tools for every ticker.

GET requests only. Engines and tools run in this process on the returned OHLCV;
storage adapters are replaced with those same frames, not synthetic data. No
provider fetch, training, publication, backtest persistence or chat persistence.
This measures functional coverage, not prospective profitability or LLM quality.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch
from urllib.parse import quote
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from app.agent.agent import StockAnalysisAgent, _extract_symbol
from app.backtesting.engine import BacktestEngine
from app.core.constants import ALL_SYMBOLS
from app.services.backtest_service import BacktestService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-errors", action="store_true", help="Retry failed history requests when resuming")
    parser.add_argument("--recheck-symbols", default="", help="Comma-separated saved symbols to inspect again when resuming")
    args = parser.parse_args()
    logging.getLogger().setLevel(logging.ERROR)
    started = datetime.now(timezone.utc).isoformat()
    elapsed_start = time.monotonic()

    def get(path):
        with urlopen(args.base_url + path, timeout=args.timeout) as response:
            return json.load(response)["data"]

    symbols = list(dict.fromkeys(get("/stocks/symbols")["symbols"]))
    results = {}
    if args.resume and args.output.is_file():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        started = previous["started_at_utc"]
        results = {r["symbol"]: r for r in previous["results"] if r["symbol"] in symbols}
        if args.retry_errors:
            results = {s: r for s, r in results.items() if "error" not in r}
        for symbol in args.recheck_symbols.upper().split(","):
            results.pop(symbol.strip(), None)
    state = threading.local()

    def load(symbol, *a, **kw):
        if symbol != state.symbol:
            raise ValueError(f"Tool requested {symbol}, expected {state.symbol}")
        return state.frame.copy(), state.layer

    def cached_backtest(self, payload, db=None):
        if payload["symbol"] != state.symbol:
            raise ValueError("Agent backtest requested the wrong ticker")
        result = state.backtests[payload["strategy"]]
        if isinstance(result, Exception):
            raise result
        return result

    def inspect(symbol):
        row = {"symbol": symbol}
        before = time.monotonic()
        try:
            payload = get("/stocks/" + quote(symbol, safe=""))
            raw = payload["rows"]
            frame = pd.DataFrame(raw)
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
            prices = frame[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
            volume = pd.to_numeric(frame["volume"], errors="coerce")
            bad_ohlc = (
                ~np.isfinite(prices).all(axis=1) | (prices <= 0).any(axis=1)
                | (prices.high + 1e-8 < prices[["open", "close", "low"]].max(axis=1))
                | (prices.low - 1e-8 > prices[["open", "close", "high"]].min(axis=1))
            )
            row["history"] = {
                "rows_returned": len(frame), "rows_reported": payload["count"],
                "truncated_by_api": len(frame) < payload["count"],
                "source_layer": payload.get("data_source"),
                "first_timestamp": str(frame.timestamp.iloc[0]),
                "last_timestamp": str(frame.timestamp.iloc[-1]),
                "sha256": hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest(),
                "invalid_ohlc_rows": int(bad_ohlc.sum()),
                "invalid_volume_rows": int((~np.isfinite(volume) | (volume < 0)).sum()),
                "duplicate_timestamps": int(frame.timestamp.duplicated().sum()),
                "invalid_timestamps": int(frame.timestamp.isna().sum()),
                "sorted_timestamps": bool(frame.timestamp.is_monotonic_increasing),
                "wrong_symbol_rows": int((frame.symbol != symbol).sum()),
            }
            row["history"]["passed"] = not any([
                row["history"][key] for key in (
                    "invalid_ohlc_rows", "invalid_volume_rows", "duplicate_timestamps",
                    "invalid_timestamps", "wrong_symbol_rows",
                )
            ]) and row["history"]["sorted_timestamps"]
            state.symbol, state.frame = symbol, frame
            state.layer = payload.get("data_source") or "gold"
            state.backtests = {}
            row["backtests"] = {}
            for strategy in ("ma_crossover", "rsi_strategy"):
                try:
                    result = BacktestEngine().run(symbol, strategy)
                    state.backtests[strategy] = result
                    fields = ("total_return", "final_capital", "win_rate", "sharpe_ratio", "maximum_drawdown", "number_of_trades")
                    metrics = {key: result[key] for key in fields}
                    equity = np.array([p["equity"] for p in result["equity_curve"]])
                    passed = bool(
                        all(np.isfinite(value) for value in metrics.values())
                        and np.isfinite(equity).all() and (equity >= 0).all()
                        and abs(metrics["final_capital"] / result["initial_capital"] - 1 - metrics["total_return"]) < 1e-9
                        and metrics["final_capital"] == equity[-1]
                        and 0 <= metrics["win_rate"] <= 1
                        and -1 <= metrics["maximum_drawdown"] <= 0
                    )
                    row["backtests"][strategy] = {
                        "passed": passed, **metrics,
                        "start_date": result["start_date"], "end_date": result["end_date"],
                        "benchmark_return": result["benchmark"]["total_return"],
                        "beat_benchmark": result["beat_benchmark"],
                    }
                except Exception as exc:
                    state.backtests[strategy] = exc
                    row["backtests"][strategy] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
            agent = StockAnalysisAgent()
            row["agent"] = {}
            for intent, question in (
                ("technical", f"Phân tích kỹ thuật {symbol}"),
                ("backtest_ma", f"Backtest MA Crossover {symbol}"),
                ("backtest_rsi", f"Backtest RSI {symbol}"),
            ):
                try:
                    answer = agent._local_reply(question, "AAPL")
                    tools = answer.get("tools", [])
                    row["agent"][intent] = {
                        "passed": bool(tools) and all(
                            t["tool_arguments"].get("symbol") == symbol
                            and not t.get("error") and not t.get("tool_result", {}).get("error") for t in tools
                        ),
                        "tools": [{"name": t["tool_name"], "symbol": t["tool_arguments"].get("symbol"), "error": t.get("error") or t.get("tool_result", {}).get("error")} for t in tools],
                    }
                except Exception as exc:
                    row["agent"][intent] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
            row["routing"] = {q: _extract_symbol(f"{q} {symbol}", "AAPL") for q in ("Giá", "Dự báo", "Backtest", "RSI", "Walk-forward")}
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["seconds"] = round(time.monotonic() - before, 3)
        return row

    def summarize():
        counts = Counter()
        for symbol, r in results.items():
            counts["symbols_checked"] += 1
            counts["history_errors"] += int("error" in r)
            if "history" in r:
                counts["history_integrity_passed"] += int(r["history"]["passed"])
                counts["histories_truncated_by_api"] += int(r["history"]["truncated_by_api"])
            counts["routing_failed"] += int(any(s != symbol for s in r.get("routing", {}).values()))
            for name, result in r.get("backtests", {}).items():
                counts[name + ("_passed" if result["passed"] else "_failed")] += 1
            for name, result in r.get("agent", {}).items():
                counts["agent_" + name + ("_passed" if result["passed"] else "_failed")] += 1
        return dict(counts)

    def save():
        report = {
            "started_at_utc": started, "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "complete": len(results) == len(symbols), "listed_symbols": len(symbols),
            "scope": __doc__, "api_history_limit": 5000,
            "configured_symbols": len(set(ALL_SYMBOLS)),
            "api_symbols_outside_config": sorted(set(symbols) - set(ALL_SYMBOLS)),
            "summary": summarize(), "results": [results[s] for s in symbols if s in results],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp = args.output.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temp.replace(args.output)

    with (
        patch("app.agent.agent.stored_symbols", return_value=frozenset(symbols)),
        patch("app.services.market_service._load_symbol_frame", side_effect=load),
        patch("app.services.market_service._load_symbol_frame_window", side_effect=load),
        patch("app.services.market_service._load_symbol_latest_uncached", side_effect=load),
        patch("app.services.market_service._cache_get", return_value=None),
        patch.object(BacktestService, "run", cached_backtest),
        ThreadPoolExecutor(max_workers=args.workers) as pool,
    ):
        pending = {pool.submit(inspect, s): s for s in symbols if s not in results}
        for future in as_completed(pending):
            symbol = pending[future]
            results[symbol] = future.result()
            if len(results) % 25 == 0 or len(results) == len(symbols):
                save()
                print(json.dumps({"elapsed_seconds": round(time.monotonic() - elapsed_start, 1), "summary": summarize()}), flush=True)
    save()


if __name__ == "__main__":
    main()
