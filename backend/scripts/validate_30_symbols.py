"""Validate that all 30 symbols return real data from Yahoo HTTP."""

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Sector-diversified S&P 500 portfolio (30 stocks, 11 sectors)
PORTFOLIO = {
    "Technology": ["AAPL", "MSFT", "GOOGL", "NVDA", "META", "ADBE", "CSCO", "ORCL"],
    "Financials": ["JPM", "BAC", "GS", "V", "MA"],
    "Healthcare": ["JNJ", "PFE", "UNH", "LLY", "MRK"],
    "Consumer Disc.": ["AMZN", "TSLA", "HD", "NKE", "MCD"],
    "Consumer Staples": ["KO", "PEP", "WMT", "PG"],
    "Energy": ["XOM", "CVX"],
    "Industrials": ["BA", "CAT"],
    "Communication": ["NFLX", "DIS"],
}

all_syms = [s for group in PORTFOLIO.values() for s in group]
print(f"Testing {len(all_syms)} symbols against Yahoo HTTP...")
print("=" * 60)

import os
os.environ["DATA_SOURCE"] = "yahoo_http"

from app.data_sources.factory import get_data_provider
import pandas as pd

p = get_data_provider("yahoo_http")
start = datetime.now(timezone.utc) - pd.Timedelta(days=3650)

ok, fail = [], []
for sector, symbols in PORTFOLIO.items():
    print(f"\n[{sector}]")
    for sym in symbols:
        try:
            df = p.get_historical_data(sym, interval="1d", start=start)
            if not df.empty and len(df) > 2000:
                first, last = df.iloc[0]["close"], df.iloc[-1]["close"]
                growth = (last / first - 1) * 100
                print(f"  [OK] {sym:5s}: {len(df):>4} rows, "
                      f"first=${first:>9.2f} -> last=${last:>9.2f} ({growth:+6.1f}%)")
                ok.append(sym)
            else:
                print(f"  [LOW] {sym:5s}: only {len(df)} rows")
                fail.append(sym)
        except Exception as e:
            print(f"  [FAIL] {sym:5s}: {str(e)[:60]}")
            fail.append(sym)

print()
print("=" * 60)
print(f"OK: {len(ok)}/{len(all_syms)}  FAIL: {len(fail)}")
if fail:
    print(f"Failed: {fail}")