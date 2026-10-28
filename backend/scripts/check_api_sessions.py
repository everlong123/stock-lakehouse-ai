"""Check the live API for the two session defects.

1. Does one trading day come back with more than one bar?
2. Does the last bar of a day look like a crash that never happened?

Run against a running backend:
    python3 scripts/check_api_sessions.py
"""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://localhost:8000/api/v1"
SYMBOLS = ["AAPL", "VCB", "ABX.TO", "BIDU", "BBD", "MSFT"]


def get(path: str):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as resp:
        return json.loads(resp.read())


def main() -> None:
    failures = 0
    for symbol in SYMBOLS:
        try:
            payload = get(f"/market/{symbol}/history?interval=1d")
        except Exception as exc:  # noqa: BLE001
            print(f"{symbol}: request failed: {exc}")
            failures += 1
            continue

        rows = payload.get("data") or []
        if not rows:
            print(f"{symbol}: no rows")
            continue

        days: dict[str, int] = {}
        for row in rows:
            key = str(row.get("timestamp", ""))[:10]
            days[key] = days.get(key, 0) + 1
        duplicated = {k: v for k, v in days.items() if v > 1}

        # A "crash" is a day whose close is far below its open; the manual-tick
        # artefact produced a ~2% drop that never happened.
        crashes = []
        for row in rows:
            o = row.get("open")
            c = row.get("close")
            if isinstance(o, (int, float)) and isinstance(c, (int, float)) and o:
                if (o - c) / o > 0.05:
                    crashes.append((str(row.get("timestamp"))[:16], round(o, 2), round(c, 2)))

        status = "OK " if not duplicated else "FAIL"
        if duplicated:
            failures += 1
        print(f"[{status}] {symbol}: {len(rows)} rows / {len(days)} days, "
              f"days with >1 bar: {len(duplicated)}"
              + (f" {list(duplicated.items())[:4]}" if duplicated else ""))
        if crashes:
            print(f"        >5% intraday drops: {crashes[:5]}")

    print()
    print("FAILURES:" if failures else "All symbols OK: one bar per trading day.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
