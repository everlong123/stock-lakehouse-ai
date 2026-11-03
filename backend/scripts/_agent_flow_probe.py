import json, sys, time
sys.path.insert(0, ".")
from app.agent.llm_client import LLMClient
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tool_registry import execute_tool, openai_tools

client = LLMClient()
tools = openai_tools()

msgs = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "Backtest chien luoc RSI cho AAPL va kiem tra walk-forward validation"},
]

total = 0
for rnd in range(1, 4):
    t0 = time.time()
    r = client.chat(msgs, tools)
    calls = r.get("tool_calls") or []
    print("round %d llm %.1fs calls=%s" % (rnd, time.time()-t0, [c['name'] for c in calls]))
    if not calls:
        print("FINAL:", (r.get('content') or '')[:400])
        break
    msgs.append({
        "role": "assistant", "content": r.get("content") or "",
        "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls],
        "raw_parts": r.get("raw_parts"),
    })
    for c in calls:
        t0 = time.time()
        args = json.loads(c["arguments"] or "{}")
        res = execute_tool(c["name"], args)
        payload = json.dumps(res, default=str)
        total += len(payload)
        print("  tool %s %.1fs payload=%.1fKB" % (c["name"], time.time()-t0, len(payload)/1024))
        msgs.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": payload})
    # approximate total prompt bytes
    approx = sum(len(json.dumps(m, default=str)) for m in msgs)
    print("  cumulative prompt bytes: %.1fKB" % (approx/1024))
print("total tool payload: %.1fKB" % (total/1024))
