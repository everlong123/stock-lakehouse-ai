import time, os, sys
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")
from app.services.backtest_service import WalkForwardService

t0=time.time()
r = WalkForwardService().run({"symbol":"AAPL","strategy":"ma_crossover","train_period_days":180,"test_period_days":30})
print("walkforward total: %.1fs windows=%d" % (time.time()-t0, r["summary"]["total_windows"]))
