"""Quick smoke-test: download REAL 10-year history via yfinance and verify shape."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_sources.factory import get_data_provider

SYMBOLS = ["AAPL", "MSFT", "AMZN", "BTC-USD", "ETH-USD", "EURUSD=X", "GBPUSD=X"]

end = datetime.now(timezone.utc)
start = end - timedelta(days=3650)  # 10 years
print(f"Requesting real OHLCV from {start.date()} to {end.date()}")

provider = get_data_provider("yfinance")
print(f"Using provider: {provider.__class__.__name__}")

for sym in SYMBOLS:
    try:
        df = provider.get_historical_data(symbol=sym, start=start, end=end, interval="1d")
        if df is None or df.empty:
            print(f"  {sym:10s} -> EMPTY (no data returned)")
        else:
            yrs = (df["timestamp"].max() - df["timestamp"].min()).days / 365.25
            print(
                f"  {sym:10s} -> {len(df):5d} rows  "
                f"{df['timestamp'].min().date()} -> {df['timestamp'].max().date()} "
                f"({yrs:.2f} years, real market data)"
            )
    except Exception as exc:
        print(f"  {sym:10s} -> ERROR: {type(exc).__name__}: {exc}")