import time, sys, json
sys.path.insert(0, ".")
from app.agent.tool_registry import execute_tool

for name, args in [
    ("run_backtest", {"symbol": "AAPL", "strategy": "rsi_strategy"}),
    ("run_walk_forward", {"symbol": "AAPL", "strategy": "rsi_strategy"}),
]:
    t0 = time.time()
    res = execute_tool(name, args)
    dt = time.time() - t0
    payload = json.dumps(res, default=str)
    print("%s: %.2fs  json=%d chars" % (name, dt, len(payload)))
    print("  top-level keys:", list(res.keys())[:20])
    for k, v in res.items():
        if isinstance(v, list):
            print("   list %s len=%d" % (k, len(v)))
        elif isinstance(v, dict):
            print("   dict %s keys=%s" % (k, list(v.keys())[:12]))
