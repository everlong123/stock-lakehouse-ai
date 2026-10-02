"""Check full inventory of US sector portfolio."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lakehouse import BronzeLayer, SilverLayer, GoldLayer

PORTFOLIO = [
    ("Technology", ["AAPL", "MSFT", "GOOGL", "NVDA", "META", "ADBE", "CSCO", "ORCL"]),
    ("Financials", ["JPM", "BAC", "GS", "V", "MA"]),
    ("Healthcare", ["JNJ", "PFE", "UNH", "LLY", "MRK"]),
    ("Consumer Disc.", ["AMZN", "TSLA", "HD", "NKE", "MCD"]),
    ("Consumer Staples", ["KO", "PEP", "WMT", "PG"]),
    ("Energy", ["XOM", "CVX"]),
    ("Industrials", ["BA", "CAT"]),
    ("Communication", ["NFLX", "DIS"]),
]

print("=" * 80)
print(f"{'Sector':<18s}  {'Symbol':<6s}  {'Bronze':>7s}  {'Silver':>7s}  {'Gold':>7s}  {'Range':<30s}")
print("=" * 80)

total_b = total_s = total_g = 0
for sector, syms in PORTFOLIO:
    print(f"\n[{sector}]")
    for sym in syms:
        b = BronzeLayer().read(sym)
        s = SilverLayer().read(sym)
        g = GoldLayer().read(sym)
        total_b += len(b); total_s += len(s); total_g += len(g)
        if len(b) == 0:
            print(f"  {sector:<16s}  {sym:<6s}  EMPTY")
        else:
            rng = f"{b['timestamp'].min().date()} -> {b['timestamp'].max().date()}"
            print(f"  {sector:<16s}  {sym:<6s}  {len(b):>7d}  {len(s):>7d}  {len(g):>7d}  {rng:<30s}")

print()
print("=" * 80)
print(f"TOTAL rows: Bronze={total_b:>7d}  Silver={total_s:>7d}  Gold={total_g:>7d}")
print(f"Symbols:    {sum(len(s) for _, s in PORTFOLIO)} US equities across {len(PORTFOLIO)} sectors")
print("=" * 80)