"""Test chitchat classifier against new patterns."""
import sys
sys.path.insert(0, '.')

from app.agent.agent import _classify_chitchat

cases = [
    ("tiếng việt đi", True),
    ("speak english please", True),
    ("trả lời bằng tiếng việt", True),
    ("ủa là sao", True),
    ("hả?", True),
    ("sao vậy", True),
    ("what?", True),
    ("tiếp đi", True),
    ("cho tôi xem thêm", True),
    ("continue", True),
    ("bạn là gì", True),
    ("what can you do", True),
    ("giúp tôi", True),
    ("à", True),
    ("bạn khoẻ ko", True),  # existing
    ("phân tích VCB", False),  # NOT chitchat
    ("backtest FPT", False),
    ("hello", True),  # greeting
]

print(f"{'INPUT':<35s} {'CHITCHAT':<10s} {'MATCH':<10s}")
print("-" * 70)
for msg, expected in cases:
    result = _classify_chitchat(msg)
    ok = (result is not None) == expected
    status = "OK" if ok else "FAIL"
    print(f"{msg!r:<35s} {str(result is not None):<10s} {status}")
    if result:
        print(f"   → {result[:70]}")