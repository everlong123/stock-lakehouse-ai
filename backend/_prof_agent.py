import time, sys
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
import os
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")

from app.core.config import settings
print("provider:", settings.llm_provider, "model:", settings.gemini_model, "timeout:", settings.gemini_timeout_seconds)
print("key set:", bool(settings.gemini_api_key.strip()))

from app.agent.llm_client import LLMClient
c = LLMClient()
print("is_configured:", c.is_configured())

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tool_registry import openai_tools
t0 = time.time()
try:
    r = c.chat([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "So sanh 3 mo hinh du bao cho AAPL"}], openai_tools())
    print("llm first pass: %.1fs" % (time.time() - t0))
    print("tool_calls:", [ (tc["name"], tc["arguments"][:120]) for tc in r.get("tool_calls") or []])
    print("content:", (r.get("content") or "")[:200])
except Exception as e:
    print("llm failed after %.1fs: %s" % (time.time() - t0, e))
