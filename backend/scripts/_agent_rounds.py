import time, sys, json
sys.path.insert(0, ".")
from app.agent.llm_client import LLMClient
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tool_registry import execute_tool, openai_tools

llm = LLMClient()
msgs = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "Backtest chien luoc RSI cho AAPL va kiem tra walk-forward validation"},
]
t0 = time.time()
first = llm.chat(msgs, openai_tools())
calls = first.get("tool_calls") or []
print("round1 %.2fs calls=%s" % (time.time() - t0, [c["name"] for c in calls]))

msgs.append({"role": "assistant", "content": first.get("content") or "",
             "tool_calls": [{"id": c["id"], "type": "function",
                             "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls],
             "raw_parts": first.get("raw_parts")})
for c in calls:
    args = json.loads(c["arguments"] or "{}")
    t0 = time.time()
    res = execute_tool(c["name"], args)
    payload = json.dumps(res, default=str)
    print("  tool %s %.2fs payload=%d chars" % (c["name"], time.time() - t0, len(payload)))
    msgs.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": payload})

for rnd in range(2, 6):
    t0 = time.time()
    r = llm.chat(msgs, openai_tools())
    rcalls = r.get("tool_calls") or []
    print("round%d %.2fs calls=%s content=%d chars" % (rnd, time.time() - t0, [c["name"] for c in rcalls], len(r.get("content") or "")))
    if not rcalls:
        break
    msgs.append({"role": "assistant", "content": r.get("content") or "",
                 "tool_calls": [{"id": c["id"], "type": "function",
                                 "function": {"name": c["name"], "arguments": c["arguments"]}} for c in rcalls],
                 "raw_parts": r.get("raw_parts")})
    for c in rcalls:
        args = json.loads(c["arguments"] or "{}")
        t0 = time.time()
        res = execute_tool(c["name"], args)
        payload = json.dumps(res, default=str)
        print("  tool %s %.2fs payload=%d chars" % (c["name"], time.time() - t0, len(payload)))
        msgs.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": payload})
