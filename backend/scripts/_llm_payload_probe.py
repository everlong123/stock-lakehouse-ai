import time, sys, json
sys.path.insert(0, ".")
from app.agent.llm_client import LLMClient
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tool_registry import execute_tool, openai_tools

llm = LLMClient()
msgs = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": sys.argv[1] if len(sys.argv) > 1 else "Backtest chien luoc RSI cho AAPL va kiem tra walk-forward validation"},
]
t0 = time.time()
first = llm.chat(msgs, openai_tools())
calls = first.get("tool_calls") or []
print("LLM #1: %.2fs calls=%s" % (time.time() - t0, [c["name"] for c in calls]))

assistant = {"role": "assistant", "content": first.get("content") or "",
             "tool_calls": [{"id": c["id"], "type": "function",
                             "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls],
             "raw_parts": first.get("raw_parts")}
msgs.append(assistant)
for c in calls:
    args = json.loads(c["arguments"] or "{}")
    t0 = time.time()
    res = execute_tool(c["name"], args)
    dt = time.time() - t0
    payload = json.dumps(res, default=str)
    print("tool %s: %.2fs payload=%d chars" % (c["name"], dt, len(payload)))
    msgs.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": payload})

t0 = time.time()
second = llm.chat(msgs, openai_tools())
print("LLM #2: %.2fs out=%d chars" % (time.time() - t0, len(second.get("content") or "")))
