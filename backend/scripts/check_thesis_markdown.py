"""Sanity-check the thesis Markdown: tables, code fences, heading order."""
import re
import sys
from pathlib import Path

# The thesis body that ships with the project. The final submission copy is
# exported from this document, so the structural checks run against it.
DOC = Path(__file__).resolve().parents[2] / "docs" / "HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md"
lines = DOC.read_text(encoding="utf-8").split("\n")
problems = []


def pipe_count(text: str) -> int:
    """Count table separators, ignoring the escaped pipes inside LaTeX.

    A LaTeX absolute value is written ``\\|y - \\hat{y}\\|`` inside a Markdown
    table so the renderer does not read it as a column boundary.
    """
    return len(re.findall(r"(?<!\\)\|", text))


def fenced_line_numbers() -> set[int]:
    """Line numbers that sit inside a fenced code block."""
    inside: set[int] = set()
    fence = None
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if fence is None:
                fence = number
            else:
                fence = None
            continue
        if fence is not None:
            inside.add(number)
    return inside


in_code = fenced_line_numbers()

# 1. Table blocks must have a consistent column count.
#    Rows inside a fenced code block are skipped: an ASCII diagram uses the
#    same pipe character for its borders.
i = 0
while i < len(lines):
    line = lines[i]
    number = i + 1
    stripped = line.replace("|", "").replace(" ", "").replace("-", "").replace(":", "")
    looks_like_table = (
        number not in in_code
        and line.startswith("|")
        and line.rstrip().endswith("|")
        and i + 1 < len(lines)
        and stripped == ""
    )
    if looks_like_table:
        width = pipe_count(line)
        j = i
        while (
            j < len(lines)
            and lines[j].startswith("|")
            and lines[j].rstrip().endswith("|")
            and (j + 1) not in in_code
        ):
            if pipe_count(lines[j]) != width:
                problems.append(
                    f"table column mismatch at line {j + 1}: "
                    f"{pipe_count(lines[j])} pipes, expected {width}"
                )
            j += 1
        i = j
    else:
        i += 1

# 2. Code fences must be balanced.
fences = sum(1 for line in lines if line.strip().startswith("```"))
if fences % 2:
    problems.append(f"unbalanced code fences: {fences}")

# 3. Heading levels must not SKIP a level, e.g. h1 -> h3.
#    Going back up (h3 -> h2) is normal and is not flagged.
previous = 0
for number, line in enumerate(lines, 1):
    if number in in_code:
        continue
    if line.startswith("#") and not line.startswith("####"):
        level = len(line) - len(line.lstrip("#"))
        if previous and level > previous + 1:
            problems.append(f"heading jump at line {number}: h{previous} -> h{level}")
        previous = level

print(f"headings: {sum(1 for l in lines if l.startswith('#'))}")
print(f"code fences: {fences}")
print(f"tables: {sum(1 for l in lines if l.strip().startswith('|---'))}")
if problems:
    print(f"\n{len(problems)} problem(s):")
    for p in problems[:30]:
        print(f"  - {p}")
else:
    print("\nNo structural problems found.")
sys.exit(1 if problems else 0)
