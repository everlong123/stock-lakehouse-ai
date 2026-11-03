import time, os, sys
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")
from app.backtesting.engine import BacktestEngine
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer

t0=time.time(); g = GoldLayer().read("AAPL"); t_gold=time.time()-t0
print("gold read: %.1fs rows=%d" % (t_gold, len(g)))
t0=time.time(); s = SilverLayer().read("AAPL"); t_silver=time.time()-t0
print("silver read: %.1fs rows=%d" % (t_silver, len(s)))

from app.backtesting.strategies import STRATEGY_MAP
from app.backtesting.portfolio import Portfolio
import pandas as pd
frame = g.sort_values("timestamp").reset_index(drop=True)
t0=time.time()
try:
    sig = STRATEGY_MAP["rsi_strategy"](parameters={}).generate_signals(frame)
    print("rsi signals: %.2fs" % (time.time()-t0))
except Exception as e:
    print("rsi signals FAILED after %.2fs: %s" % (time.time()-t0, e))

t0=time.time()
try:
    r = BacktestEngine().run(symbol="AAPL", strategy_name="ma_crossover")
    print("ma_crossover backtest: %.1fs" % (time.time()-t0))
except Exception as e:
    print("ma backtest FAILED after %.1fs: %s" % (time.time()-t0, e))
