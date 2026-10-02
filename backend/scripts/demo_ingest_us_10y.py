"""Ingest 10-year data for 33 sector-diversified US stocks.

Pipeline per symbol: Bronze -> Silver -> Gold with quality checks.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
os.environ["DATA_SOURCE"] = "yahoo_http"

from app.pipelines import run_symbol_pipeline
import pandas as pd
import time

# Sector-diversified portfolio (11 sectors)
PORTFOLIO = [
    # Technology
    "AAPL", "MSFT", "GOOGL", "NVDA", "META", "ADBE", "CSCO", "ORCL",
    # Financials
    "JPM", "BAC", "GS", "V", "MA",
    # Healthcare
    "JNJ", "PFE", "UNH", "LLY", "MRK",
    # Consumer Disc.
    "AMZN", "TSLA", "HD", "NKE", "MCD",
    # Consumer Staples
    "KO", "PEP", "WMT", "PG",
    # Energy
    "XOM", "CVX",
    # Industrials
    "BA", "CAT",
    # Communication
    "NFLX", "DIS",
]

START = datetime.now(timezone.utc) - pd.Timedelta(days=3650)  # 10 years

print("=" * 70)
print(f"Ingesting {len(PORTFOLIO)} US stocks (10-year lookback via yahoo_http)")
print("=" * 70)

ok, fail = [], []
total_start = time.time()

for i, sym in enumerate(PORTFOLIO, 1):
    t0 = time.time()
    try:
        r = run_symbol_pipeline(sym, interval="1d", start=START, source_name="yahoo_http")
        elapsed = round(time.time() - t0, 1)
        n = r["records_processed"]
        q = r["quality"]["quality_status"]
        print(f"  [{i:2}/{len(PORTFOLIO)}] {sym:5s}: rows={n:>4} quality={q:>7} time={elapsed:>5.1f}s")
        if q == "passed":
            ok.append(sym)
        else:
            fail.append((sym, f"quality={q}"))
    except Exception as exc:
        elapsed = round(time.time() - t0, 1)
        msg = f"{type(exc).__name__}: {str(exc)[:120]}"
        print(f"  [{i:2}/{len(PORTFOLIO)}] {sym:5s}: FAIL ({elapsed:>4.1f}s) {msg}")
        fail.append((sym, msg))

total_elapsed = round(time.time() - total_start, 1)

print()
print("=" * 70)
print(f"Total time: {total_elapsed}s")
print(f"OK:  {len(ok)}/{len(PORTFOLIO)}")
print(f"FAIL: {len(fail)}/{len(PORTFOLIO)}")
if fail:
    for sym, m in fail:
        print(f"  - {sym}: {m}")
print()
print("Done. Run scripts/check_inventory.py to see updated counts.")