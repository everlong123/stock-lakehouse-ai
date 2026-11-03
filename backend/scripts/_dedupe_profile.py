import cProfile, io, pstats, sys, time
sys.path.insert(0, ".")
import pandas as pd

from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.dedupe import dedupe_same_bars
from app.services.market_service import _load_symbol_frame

frame, _ = _load_symbol_frame("AAPL")
bronze_like = frame[["symbol", "timestamp", "open", "high", "low", "close", "adj_close", "volume", "source", "ingestion_time"]].copy()

pr = cProfile.Profile()
pr.enable()
for _ in range(5):
    dedupe_same_bars(bronze_like)
pr.disable()
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(14)
print(s.getvalue())
