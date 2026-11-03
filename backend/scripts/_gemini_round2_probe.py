import json, sys, time
sys.path.insert(0, ".")
from app.agent.llm_client import LLMClient
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tool_registry import openai_tools

client = LLMClient()
tools = openai_tools()

msgs = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "Backtest chien luoc RSI cho AAPL va kiem tra walk-forward validation"},
]

t0 = time.time()
r1 = client.chat(msgs, tools)
print("round1 %.1fs calls=%s" % (time.time()-t0, [c['name'] for c in (r1.get('tool_calls') or [])]))

calls = r1.get('tool_calls') or []
msgs.append({
    "role": "assistant", "content": r1.get("content") or "",
    "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls],
    "raw_parts": r1.get("raw_parts"),
})

big = json.dumps({"symbol":"AAPL","strategy":"rsi_strategy","summary":{"total_windows":175,"passed_windows":159,"failed_windows":16,"avg_train_return":0.09,"avg_test_return":0.0024,"avg_test_sharpe":0.18,"avg_test_max_drawdown":-0.0057,"avg_test_win_rate":0.106,"total_test_trades":32,"return_consistency":0.106,"overfitting_ratio":37.29},"windows":[{"window_id":i,"train_period":"2020-01-01 to 2020-06-01","test_period":"2020-06-02 to 2020-07-02","train_return":0.09,"test_return":0.002,"test_sharpe":0.18,"test_max_drawdown":-0.005,"test_win_rate":0.1,"test_num_trades":1,"passed":True,"error":None} for i in range(175)]})
small = json.dumps({"symbol":"AAPL","strategy":"rsi_strategy","summary":{"total_windows":175,"passed_windows":159,"avg_test_return":0.0024},"windows":[]})

for label, filler in (("small(0.2KB)", small), ("big(47KB)", big)):
    msgs2 = list(msgs)
    msgs2.append({"role":"tool","tool_call_id":calls[0]["id"],"name":calls[0]["name"],"content":filler})
    t0 = time.time()
    try:
        r2 = client.chat(msgs2, tools)
        print("%s round2 %.1fs OK -> %r" % (label, time.time()-t0, (r2.get('content') or '')[:200]))
    except Exception as exc:
        print("%s round2 %.1fs FAIL %s" % (label, time.time()-t0, str(exc)[:300]))
