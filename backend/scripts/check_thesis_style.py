"""Flag sentences that read like machine-generated filler.

The rules are deliberately conservative: only patterns that are almost never
used by a human writing an academic thesis are flagged.
"""
import re
import sys
from collections import Counter
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md"
text = DOC.read_text(encoding="utf-8")

# 1. Empty superlatives and filler openings that carry no information.
FILLER = [
    r"\bTrong (?:thế giới|hiện đại|xã hội) (?:của )?(?:ngày )?nay\b",
    r"\bVới sự phát triển (?:nhanh chóng|cực nhanh) của\b",
    r"\bđã và đang (?:phát triển|trở thành) (?:một )?(?:xu hướng|xu thế)\b",
    r"\bkhông thể phủ nhận\b",
    r"\bđóng vai trò (?:quan trọng|cốt lõi) (?:trong|đối với)\b",
    r"\bđóng vai trò (?:then chốt|không thể thiếu)\b",
    r"\b(?:nói ngắn gọn|nói một cách ngắn gọn)\b",
    r"\bđiều đó có nghĩa là\b",
    r"\bHãy (?:xem|hiểu|tưởng tượng)\b",
    r"\bMột cách (?:chung|khái quát)\b",
    r"\b(?:Tóm lại|Tổng kết lại|Tóm tắt lại)\b",
    r"\bkhông chỉ .{1,40} mà còn\b",
    r"\b(?:cần thiết|quan trọng) (?:không chỉ|không những)\b",
    r"\bđóng góp (?:đáng kể|quan trọng) (?:cho|đối với) (?:nghiên cứu|lĩnh vực)\b",
    r"\b(?:một cách|hơn nữa) (?:đáng chú ý|đáng lưu ý) là\b",
    r"\b(?:rõ ràng|hiển nhiên) là\b",
    r"\bBằng cách (?:đó|thế|áp dụng)\b",
    r"\bchúng ta (?:sẽ|có thể|hãy)\b",
    r"\b(?:nói cách khác|hay nói cách khác)\b",
    r"\b(?:kết quả này|điều này) (?:cho thấy|chứng minh) (?:rằng )?(?:rằng )?\b",
    r"\b(?:rất|đặc biệt|khá) (?:quan trọng|ý nghĩa)\b",
    r"\bvô cùng\b|\bcực kỳ\b|\bhết sức\b",
]

# 2. Overused academic connectors that AI leans on.
CONNECTORS = [
    r"\bTuy nhiên, .{0,20}(?:cần lưu ý|đáng chú ý) rằng\b",
    r"\bĐiều đáng chú ý là\b",
    r"\bĐiều quan trọng là\b",
    r"\bCó thể nói\b",
    r"\bTheo như\b",
    r"\bBước này\b",
    r"\bTiếp theo, .{0,30} sẽ\b",
    r"\bcuối cùng, .{0,30}(?:chúng ta|sẽ)\b",
    r"\bVậy (?:là|như vậy)\b",
]

# 3. Em-dash overuse: humans writing Vietnamese theses use them sparingly.
EM_DASH = re.compile(r"—")

sentences = re.split(r"(?<=[.!?])\s+", text)
hits = Counter()
examples = {}

patterns = [(p, "filler") for p in FILLER] + [(p, "connector") for p in CONNECTORS]
for sent in sentences:
    if len(sent) < 25:
        continue
    for pattern, kind in patterns:
        if re.search(pattern, sent, flags=re.IGNORECASE):
            hits[kind] += 1
            examples.setdefault(kind, []).append(sent.strip()[:130])
            break

print("=== Machine-filler scan ===")
if not hits:
    print("No filler patterns found.")
for kind, count in hits.items():
    print(f"\n{kind}: {count} sentence(s)")
    for ex in examples[kind][:5]:
        print(f"  - {ex}")

em_count = len(EM_DASH.findall(text))
print(f"\nem-dashes: {em_count}")

# 4. Sentence-length distribution: AI text tends toward uniform short bursts.
lengths = [len(s.split()) for s in sentences if len(s.split()) > 3]
if lengths:
    lengths.sort()
    median = lengths[len(lengths) // 2]
    short = sum(1 for n in lengths if n < 12) / len(lengths)
    long_ = sum(1 for n in lengths if n > 45) / len(lengths)
    print(f"sentences: {len(lengths)}, median words: {median}")
    print(f"share < 12 words: {short:.1%}, share > 45 words: {long_:.1%}")

sys.exit(1 if sum(hits.values()) > 3 else 0)
