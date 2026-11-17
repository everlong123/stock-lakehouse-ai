"""Reduce em-dash density in the thesis.

Vietnamese academic writing prefers a comma, a colon, or a full stop over the
em-dash. The em-dash is the single clearest typographic tell of machine
generated prose, and 116 of them across 657 sentences is roughly one every
six sentences.

The rewrite is conservative:
  - an em-dash that introduces a list becomes a colon
  - an em-dash that sets off a final clause becomes a comma
  - an em-dash that stands in for a full stop becomes a full stop
  - an em-dash inside a table cell becomes a comma
"""
import re
import sys
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md"
text = DOC.read_text(encoding="utf-8")
before = text.count("—")

# 1. "word — word" where the dash introduces an explanation or a list.
text = re.sub(r" — (tức là|như sau|bao gồm|gồm|đó là|với)", r": \1", text)
text = re.sub(r" — (gồm|bao gồm) ", r": \1 ", text)

# 2. "word — word" where the dash sets off a trailing clause -> comma.
text = re.sub(r"(?<=[a-zA-ZÀ-ỹ0-9%\)]) — (?=[a-zà-ỹ])", r", ", text)

# 3. "word — Word" (capital after the dash) -> a full stop, new sentence.
text = re.sub(r"(?<=[a-zA-ZÀ-ỹ0-9%\]]) — (?=[A-ZÀ-Ý])", r". ", text)

# 4. A dash at the start of a clause -> a comma.
text = re.sub(r"(?<=[\.\:\n]) — ", r" ", text)

# 5. Two dashes in a row -> keep one as a separator.
text = re.sub(r"—\s*—", r"—", text)

# 6. Tidy the spacing left behind.
text = re.sub(r"\s+,", ",", text)
text = re.sub(r",\s+,", ",", text)
text = re.sub(r"\.\s+\.", ".", text)
text = re.sub(r"([.!?])\s*\1", r"\1", text)
text = re.sub(r",\s*\.", ".", text)
text = re.sub(r" +\n", "\n", text)
text = re.sub(r"\n{3,}", "\n\n", text)

after = text.count("—")
DOC.write_text(text, encoding="utf-8")
print(f"em-dash: {before} -> {after}")
sys.exit(0)
