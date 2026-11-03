import json, sys, time
sys.path.insert(0, ".")
from app.agent.llm_client import LLMClient, _convert_to_gemini_contents, _convert_to_gemini_tools
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tool_registry import openai_tools
from app.core.config import settings

print("gemini_model:", settings.gemini_model)
print("base_url:", settings.gemini_base_url)
print("timeout:", settings.gemini_timeout_seconds)

client = LLMClient()

def probe(label, filler):
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Backtest chien luoc RSI cho AAPL va kiem tra walk-forward validation"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_0", "type": "function", "function": {"name": "run_walk_forward", "arguments": "{\"symbol\":\"AAPL\"}"}}]},
        {"role": "tool", "tool_call_id": "call_0", "name": "run_walk_forward", "content": filler},
    ]
    t0 = time.time()
    try:
        r = client.chat(msgs, openai_tools())
        print(label, "-> %.1fs ok content=%r tools=%d" % (time.time()-t0, (r.get('content') or '')[:120], len(r.get('tool_calls') or [])))
    except Exception as exc:
        print(label, "-> %.1fs FAIL %s" % (time.time()-t0, str(exc)[:200]))

small = json.dumps({"symbol":"AAPL","summary":{"total_windows":175,"avg_test_return":0.0024},"windows":[]})
probe("small payload (%.1fKB)" % (len(small)/1024), small)

big = json.dumps({"symbol":"AAPL","summary":{"total_windows":175},"windows":[{"window_id":i,"train_period":"2020-01-01 to 2020-06-01","test_period":"2020-06-02 to 2020-07-02","train_return":0.09,"test_return":0.002,"test_sharpe":0.18,"test_max_drawdown":-0.005,"test_win_rate":0.1,"test_num_trades":1,"passed":True,"error":None} for i in range(175)]})
probe("big payload (%.1fKB)" % (len(big)/1024), big)
