"""Quick debug: why 'phân tích VCB' and 'backtest FPT' didn't trigger tools."""
import sys
sys.path.insert(0, '.')

from app.agent.agent import _classify_chitchat, _has_finance_intent, _extract_symbol

cases = [
    "phân tích VCB",
    "backtest FPT",
    "so sánh model VCB",
    "giúp tôi",
]

for msg in cases:
    norm = msg.strip().lower()
    chitchat = _classify_chitchat(msg)
    intent = _has_finance_intent(norm)
    sym = _extract_symbol(msg, "DEFAULT")
    print(f"msg={msg!r}")
    print(f"  chitchat={chitchat is not None}")
    print(f"  intent={intent}")
    print(f"  symbol={sym!r}")
    print()
