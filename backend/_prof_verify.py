import time, os, sys, json
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")
from app.backtesting.engine import BacktestEngine
from app.services.backtest_service import WalkForwardService

for strat in ("ma_crossover", "rsi_strategy"):
    t0=time.time()
    r = BacktestEngine().run(symbol="AAPL", strategy_name=strat)
    print("%-14s %.2fs return=%.6f trades=%s sharpe=%.4f dd=%.4f pf=%.4f" % (
        strat, time.time()-t0, r["total_return"], r["number_of_trades"],
        r["sharpe_ratio"], r["maximum_drawdown"], r["profit_factor"]))

t0=time.time()
w = WalkForwardService().run({"symbol":"AAPL","strategy":"ma_crossover"})
print("walkforward %.1fs windows=%d passed=%d avg_test_return=%.4f consistency=%.3f" % (
    time.time()-t0, w["summary"]["total_windows"], w["summary"]["passed_windows"],
    w["summary"]["avg_test_return"], w["summary"]["return_consistency"]))
