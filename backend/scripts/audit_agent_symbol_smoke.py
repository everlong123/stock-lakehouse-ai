"""Exercise real HTTP agent requests and verify ticker/tool/error fidelity.

These POST requests create audit chat messages in the configured application DB.
They do not send messages to other people or ingest/train/publish forecasts.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = [
        ("Giá WBA hôm nay", "WBA", {"query_stock_data", "get_market_summary"}, False),
        ("Giá BK hôm nay", "BK", {"query_stock_data", "get_market_summary"}, False),
        ("Backtest AVB", "AVB", {"run_backtest"}, True),
        ("Walk-forward RSI AAPL", "AAPL", {"run_walk_forward"}, False),
    ]
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "base_url": args.base_url, "results": []}
    for question, symbol, expected_tools, expect_error in cases:
        started = time.monotonic()
        row = {"question": question, "expected_symbol": symbol, "expected_tools": sorted(expected_tools)}
        try:
            request = Request(
                args.base_url + "/agent/chat",
                data=json.dumps({"message": question, "symbol": "AAPL", "session_id": "audit-symbols-20261119-fixed"}).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urlopen(request, timeout=100) as response:
                row["http_status"] = response.status
                row["response"] = json.load(response)
            data = row["response"]["data"]
            tools = data.get("tools", [])
            symbol_tools = [t for t in tools if "symbol" in t.get("tool_arguments", {})]
            row["passed"] = (
                bool(symbol_tools)
                and all(t["tool_arguments"]["symbol"] == symbol for t in symbol_tools)
                and any(t["tool_name"] in expected_tools for t in symbol_tools)
                and any(bool(t.get("error")) for t in symbol_tools) == expect_error
                and bool(data.get("assistant_message"))
            )
            if symbol == "AAPL":
                row["passed"] &= any(
                    t["tool_name"] == "run_walk_forward" and t["tool_arguments"].get("strategy") == "rsi_strategy"
                    for t in tools
                )
        except Exception as exc:
            row.update(passed=False, error=f"{type(exc).__name__}: {exc}")
        row["seconds"] = round(time.monotonic() - started, 2)
        report["results"].append(row)
        report["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["complete"] = len(report["results"]) == len(cases)
        report["passed"] = all(r["passed"] for r in report["results"])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({k: v for k, v in row.items() if k != "response"}), flush=True)


if __name__ == "__main__":
    main()
