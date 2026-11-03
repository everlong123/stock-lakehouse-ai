import sys, os, time
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")
from app.agent.agent import StockAnalysisAgent

a = StockAnalysisAgent()
print("llm configured:", a.llm.is_configured())
t0=time.time()
r = a.reply("Phan tich ky thuat AAPL", default_symbol="AAPL")
print("reply returned:", type(r), "in %.1fs" % (time.time()-t0))
if r is None:
    print("!!! reply returned None")
else:
    print("keys:", list(r.keys()))
    print("msg:", (r.get("assistant_message") or "")[:200])
    print("tools:", [t.get("tool_name") for t in r.get("tools") or []])
