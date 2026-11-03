"""Validate every symbol in GLOBAL_SYMBOLS against the Yahoo provider.

A ticker that is in the universe but has no Yahoo listing will 404 on every
fetch, so the auto-refresh pass logs a warning for it and moves on. That is
noise, not data loss, but it hides real failures. This checks the whole
universe once and reports the dead tickers.

Run inside the backend container:

    docker exec stock-lakehouse-backend python scripts/check_universe_alive.py
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import GLOBAL_SYMBOLS
from app.core.logging_config import get_logger
from app.data_sources.yahoo_http_provider import YahooHttpProvider

logger = get_logger(__name__)

WORKERS = 6


def probe(provider: YahooHttpProvider, symbol: str) -> tuple[str, bool, str]:
    try:
        frame = provider.get_historical_data(
            symbol=symbol,
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime.now(timezone.utc),
            interval="1d",
        )
    except Exception as exc:  # noqa: BLE001
        return symbol, False, f"{type(exc).__name__}: {str(exc)[:90]}"
    if frame is None or frame.empty:
        return symbol, False, "empty frame"
    return symbol, True, f"{len(frame)} rows, last={frame.iloc[-1].get('timestamp')}"


def main() -> None:
    provider = YahooHttpProvider()
    symbols = list(GLOBAL_SYMBOLS)
    print(f"probing {len(symbols)} symbols with {WORKERS} workers ...\n")

    alive: list[str] = []
    dead: list[tuple[str, str]] = []

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(probe, provider, s): s for s in symbols}
        for done, future in enumerate(as_completed(futures), start=1):
            symbol, ok, detail = future.result()
            (alive if ok else dead).append(symbol if ok else (symbol, detail))
            if done % 100 == 0:
                print(f"  {done}/{len(symbols)} probed", flush=True)

    print(f"\nalive: {len(alive)} / {len(symbols)}")
    print(f"dead : {len(dead)}")
    for symbol, detail in sorted(dead):
        print(f"  x {symbol:12s} {detail}")


if __name__ == "__main__":
    main()
