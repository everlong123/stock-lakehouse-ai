"""Replay the provider fetch for symbols that are missing a trading day.

Yahoo's period1 turned out to be inclusive, so the "start = last bar + 1 day"
watermark is not the cause of the missing days. The remaining candidate is
the row being fetched and then DROPPED before it reaches Bronze.

This replays the exact provider path - raw Yahoo payload, then
`_normalize_ohlc` - for a symbol that lacks the day, and reports which rows
survive. It imports the provider module directly, bypassing the app package
(the WSL python has no pydantic), so it re-implements the two calls the
provider makes.

    python3 scripts/replay_provider_for_day.py ABX.TO BBD 2026-10-21
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import pandas as pd
import requests

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

PRICE_COLS = ["open", "high", "low", "close"]


def raw_fetch(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    params = {
        "period1": int(start.timestamp()),
        "period2": int(end.timestamp()),
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
    quote = result["indicators"]["quote"][0]
    adj = result["indicators"].get("adjclose", [{}])[0].get("adjclose", [])
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(result.get("timestamp", []), unit="s", utc=True),
        "open": quote.get("open", []),
        "high": quote.get("high", []),
        "low": quote.get("low", []),
        "close": quote.get("close", []),
        "volume": quote.get("volume", []),
        "adj_close": adj if adj else quote.get("close", []),
    })
    return df.dropna(subset=["close"]).reset_index(drop=True)


def normalize(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mirror `YahooHttpProvider._normalize_ohlc`."""
    out = df.copy()
    for col in PRICE_COLS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    lo = out[PRICE_COLS].min(axis=1)
    hi = out[PRICE_COLS].max(axis=1)
    unrepairable = (
        (out[PRICE_COLS] <= 0).any(axis=1)
        | out[PRICE_COLS].isna().any(axis=1)
        | ((hi - lo) <= 0)
    )
    dropped = out[unrepairable].copy()
    out = out[~unrepairable].copy()
    if not out.empty:
        out["high"] = out[PRICE_COLS].max(axis=1)
        out["low"] = out[PRICE_COLS].min(axis=1)
    return out, dropped


def main() -> None:
    symbols = sys.argv[1:-1] or ["ABX.TO", "BBD"]
    target = sys.argv[-1] if len(sys.argv) > 1 else "2026-10-21"
    t = datetime.fromisoformat(target).replace(tzinfo=timezone.utc)
    start = t.replace(hour=0, minute=0) - pd.Timedelta(days=10)
    end = t + pd.Timedelta(days=10)

    for symbol in symbols:
        print(f"=== {symbol} (target {target}) ===")
        try:
            raw = raw_fetch(symbol, start, end)
        except Exception as exc:  # noqa: BLE001
            print(f"  fetch failed: {exc}\n")
            continue
        raw["day"] = raw["timestamp"].dt.date
        kept, dropped = normalize(raw)
        print("  RAW rows:")
        for _, r in raw.iterrows():
            mark = "  <-- TARGET" if str(r["day"]) == target else ""
            print(f"    {r['timestamp']:%Y-%m-%d %H:%M} o={r['open']} h={r['high']} "
                  f"l={r['low']} c={r['close']} v={r['volume']}{mark}")
        if not dropped.empty:
            print("  DROPPED by _normalize_ohlc:")
            for _, r in dropped.iterrows():
                print(f"    {r['timestamp']:%Y-%m-%d %H:%M} o={r['open']} h={r['high']} "
                      f"l={r['low']} c={r['close']} v={r['volume']}")
        else:
            print("  DROPPED by _normalize_ohlc: none")
        has = target in set(kept["day"].astype(str)) if not kept.empty else False
        print(f"  target present after normalize? {has}")
        print()


if __name__ == "__main__":
    main()
