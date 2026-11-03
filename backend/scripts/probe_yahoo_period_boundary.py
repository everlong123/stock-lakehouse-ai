"""Verify Yahoo's period1 boundary semantics for daily bars.

The incremental refresh computes the next fetch as

    start = last_bar_timestamp + 1 day

For a US ticker whose daily bar is stamped at the session OPEN in UTC
(13:30 UTC in EDT, 14:30 UTC in EST), that makes ``start`` land EXACTLY on
the next day's bar timestamp. If Yahoo treats ``period1`` as exclusive, the
bar for that day is never returned - the symbol silently advances to the day
after and the gap becomes permanent.

This script calls the chart API with two different period1 values for the
same symbol and prints the first timestamps returned, so the boundary
semantics are observed rather than assumed.

    python3 scripts/probe_yahoo_period_boundary.py AAPL
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import requests

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def fetch(symbol: str, period1: datetime, period2: datetime) -> list[str]:
    params = {
        "period1": int(period1.timestamp()),
        "period2": int(period2.timestamp()),
        "interval": "1d",
        "includeAdjustedClose": "true",
        "events": "history",
    }
    resp = requests.get(
        CHART_URL.format(symbol=symbol),
        params=params,
        headers={"User-Agent": UA},
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    return [datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            for t in result.get("timestamp", [])]


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    end = datetime(2026, 10, 27, tzinfo=timezone.utc)

    # A: period1 exactly on a bar's own timestamp (13:30 UTC).
    a = fetch(symbol, datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc), end)
    # B: period1 at the same day's midnight.
    b = fetch(symbol, datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc), end)
    # C: period1 one second before the bar.
    c = fetch(symbol, datetime(2026, 10, 21, 13, 29, 59, tzinfo=timezone.utc), end)

    print(f"=== {symbol} ===")
    print(f"period1 = 2026-10-21 13:30:00 (exactly a bar stamp)")
    print(f"   -> {a[:4]}")
    print(f"period1 = 2026-10-21 00:00:00 (midnight)")
    print(f"   -> {b[:4]}")
    print(f"period1 = 2026-10-21 13:29:59 (one second before)")
    print(f"   -> {c[:4]}")

    has = lambda rows, day: any(r.startswith(day) for r in rows)  # noqa: E731
    print()
    print(f"  2026-10-21 present with period1=13:30:00 ? {has(a, '2026-10-21')}")
    print(f"  2026-10-21 present with period1=00:00:00 ? {has(b, '2026-10-21')}")
    print(f"  2026-10-21 present with period1=13:29:59 ? {has(c, '2026-10-21')}")


if __name__ == "__main__":
    main()
