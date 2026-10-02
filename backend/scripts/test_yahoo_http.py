"""Test Yahoo HTTP provider directly."""

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_sources.factory import get_data_provider
import pandas as pd
import time

p = get_data_provider("yahoo_http")
print(f"Provider: {p.source_name}")
print()

start = datetime.now(timezone.utc) - pd.Timedelta(days=3650)

t0 = time.time()
# Use 10-year lookback for richer data
for sym in ["AAPL", "MSFT", "GOOGL", "NVDA"]:
    try:
        df = p.get_historical_data(sym, interval="1d", start=start)
        if not df.empty:
            print(f"{sym}: {len(df)} rows  range=[{df['timestamp'].min().date()} -> {df['timestamp'].max().date()}]")
            print(f"  first close: {df.iloc[0]['close']}, last close: {df.iloc[-1]['close']}")
        else:
            print(f"{sym}: EMPTY")
    except Exception as e:
        print(f"{sym}: FAIL - {e}")

print(f"\nTotal time: {time.time()-t0:.1f}s")