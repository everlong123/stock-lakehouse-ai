import time, sys, json
sys.path.insert(0, ".")
from app.agent.llm_client import LLMClient
from app.agent.tool_registry import openai_tools, execute_tool

llm = LLMClient()
print("configured:", llm.is_configured())

msgs = [
    {"role": "system", "content": "Bạn là trợ lý phân tích chứng khoán."},
    {"role": "user", "content": "Phan tich ky thuat chung khoan AAPL 1 nam gan nhat"},
]
t0 = time.time()
first = llm.chat(msgs, openai_tools())
print("LLM call #1: %.2fs tool_calls=%s" % (time.time() - t0, [c["name"] for c in first.get("tool_calls") or []]))

for call in first.get("tool_calls") or []:
    args = json.loads(call["arguments"] or "{}")
    t0 = time.time()
    res = execute_tool(call["name"], args)
    print("tool %s: %.2fs" % (call["name"], time.time() - t0))
    msgs.append({"role": "assistant", "content": first.get("content") or "",
                 "tool_calls": [{"id": call["id"], "type": "function",
                                 "function": {"name": call["name"], "arguments": call["arguments"]}}],
                 "raw_parts": first.get("raw_parts")})
    msgs.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                 "content": json.dumps(res, default=str)})

t0 = time.time()
second = llm.chat(msgs, openai_tools())
print("LLM call #2: %.2fs len=%s" % (time.time() - t0, len(second.get("content") or "")))
