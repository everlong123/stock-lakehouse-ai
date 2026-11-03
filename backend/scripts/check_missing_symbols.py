"""Probe Yahoo Finance for the symbols that have no data in the lake.

The coverage report listed 16 symbols from GLOBAL_SYMBOLS that never landed in
any layer. Most are delisted, so they can never produce data. This probes the
provider directly to tell the two groups apart, and reports the last trade date
for the ones that still respond.

Run inside the backend container:

    docker exec stock-lakehouse-backend python scripts/check_missing_symbols.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import get_logger
from app.data_sources.yahoo_http_provider import YahooHttpProvider

logger = get_logger(__name__)

MISSING = [
    "823.HK", "9613.T", "ABV", "ALTM", "ATVI", "AVTE", "ERJ", "GOL",
    "HEIA.DE", "NCM.AX", "PRTY.L", "ROG.SW", "SBSA", "STLA.PA", "TTM",
    "WPL.AX",
]


def main() -> None:
    provider = YahooHttpProvider()
    alive = []
    dead = []

    for symbol in MISSING:
        try:
            frame = provider.get_historical_data(
                symbol=symbol,
                start=datetime(2025, 1, 1),
                end=datetime(2026, 10, 27),
                interval="1d",
            )
        except Exception as exc:  # noqa: BLE001
            dead.append((symbol, f"error: {type(exc).__name__}: {exc}"))
            print(f"  {symbol:10s} DEAD   {type(exc).__name__}: {exc}")
            continue

        if frame is None or frame.empty:
            dead.append((symbol, "empty frame"))
            print(f"  {symbol:10s} DEAD   provider returned empty frame")
            continue

        last = frame.iloc[-1]
        ts = last.get("timestamp") or last.get("date")
        close = last.get("close")
        alive.append((symbol, str(ts), close))
        print(f"  {symbol:10s} ALIVE  rows={len(frame):5d} last={ts} close={close}")

    print()
    print(f"alive: {len(alive)} / {len(MISSING)}")
    for symbol, ts, close in alive:
        print(f"  + {symbol:10s} last={ts} close={close}")
    print(f"dead: {len(dead)}")
    for symbol, why in dead:
        print(f"  - {symbol:10s} {why}")


if __name__ == "__main__":
    main()
