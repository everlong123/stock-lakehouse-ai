import sys, os
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")
import pandas as pd
from app.backtesting.strategies.rsi_strategy import RSIStrategy

# 1. synthetic edge case that used to raise
close = pd.Series([100.0]*30 + [95.0]*30 + [105.0]*30)
frame = pd.DataFrame({"close": close})
sig = RSIStrategy(parameters={}).generate_signals(frame)
print("synthetic OK:", sig.value_counts().to_dict())

# 2. real data from the lakehouse
from app.lakehouse.gold import GoldLayer
g = GoldLayer().read("AAPL")
sig2 = RSIStrategy(parameters={}).generate_signals(g)
print("AAPL OK:", sig2.value_counts().to_dict(), "dtype", sig2.dtype)
print("first 8:", sig2.head(8).tolist())
print("nan count:", sig2.isna().sum())
