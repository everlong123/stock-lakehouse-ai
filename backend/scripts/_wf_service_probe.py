import json, sys, time
sys.path.insert(0, ".")
from app.services.backtest_service import WalkForwardService

t0 = time.time()
res = WalkForwardService().run({"symbol": "AAPL", "strategy": "rsi_strategy"})
print("WalkForwardService total %.2fs" % (time.time()-t0))
print("payload bytes:", len(json.dumps(res, default=str)))
