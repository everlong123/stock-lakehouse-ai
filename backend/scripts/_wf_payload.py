import json, time, sys
sys.path.insert(0, ".")
from app.agent.tools.walkforward_tools import run_walk_forward
from app.backtesting.walk_forward import WalkForwardValidator

t0 = time.time()
res = WalkForwardValidator().run(symbol="AAPL", strategy_name="rsi_strategy")
t1 = time.time()
payload = json.dumps(res, default=str)
print("walk_forward wall %.2fs" % (t1 - t0))
print("json payload bytes:", len(payload))
print("keys:", list(res.keys()))
print("summary:", json.dumps(res.get("summary"), indent=1)[:800])
print("windows:", len(res.get("windows") or []))
