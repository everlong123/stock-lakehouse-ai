"""Test Stooq provider."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_sources.factory import get_data_provider

p = get_data_provider("stooq")
print(f"Provider: {p.source_name}")

import time
t0 = time.time()
for sym in ["AAPL", "MSFT", "GOOGL"]:
    df = p.get_historical_data(sym, interval="1d")
    if not df.empty:
        print(f"\n{sym}: {len(df)} rows, range [{df['timestamp'].min().date()} -> {df['timestamp'].max().date()}]")
        print(df.tail(3).to_string(index=False))
    else:
        print(f"{sym}: EMPTY")

print(f"\nTotal time: {time.time()-t0:.1f}s")