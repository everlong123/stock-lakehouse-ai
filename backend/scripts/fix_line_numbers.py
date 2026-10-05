"""Fix bad line-number markers - more aggressive: strip "    N|" anywhere."""
import re
from pathlib import Path

fixed_files = 0
fixed_lines = 0
for p in [
    "frontend/src/pages/Dashboard.tsx",
    "frontend/src/pages/MarketData.tsx",
    "frontend/src/pages/SystemStatus.tsx",
    "frontend/src/components/agent/ChatBox.tsx",
]:
    path = Path(p)
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    new_lines = []
    for line in text.split("\n"):
        original = line
        # Strip "    N| " or "    N|" anywhere in line - the artifact has form
        # "    10| Sparkles," or just "    10|"
        new_line = re.sub(r"^\s*\d+\|\s?", "", line)
        if new_line != line:
            fixed_lines += 1
            line = new_line
        # Also strip middle-of-line patterns like "background: white" preceded by "20|"
        new_line = re.sub(r"\s+\d+\|\s?(?=[A-Za-z_])", "", line)
        if new_line != line:
            fixed_lines += 1
            line = new_line
        new_lines.append(line)
    new_text = "\n".join(new_lines)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        fixed_files += 1
        print(f"FIXED {p}")
print(f"\nTotal files fixed: {fixed_files}, total lines cleaned: {fixed_lines}")