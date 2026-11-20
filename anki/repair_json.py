"""Repair JSON deck files that contain raw double quotes inside string values.

WHY THIS EXISTS
---------------
The deck content is authored as JSON. The ``answer`` fields carry prose that
legitimately contains double quotes (for example: ``chuoi "tot nhat den
kem nhat"``). In JSON those characters MUST be escaped. Writing them raw
produces a file that Python's ``json.load`` rejects.

Rather than hand-escaping every quote in every file - which is exactly the
kind of tedious, error-prone work that silently corrupts content - this
script repairs the files mechanically.

HOW IT WORKS
------------
The deck files store one field per line, in a fixed shape::

    "answer": "<value text>",

So the repair is line-scoped and therefore unambiguous: for a line that
holds a string field, the value starts after the opening quote and ends at
the LAST quote of the line. Every raw (unescaped) double quote inside that
span is escaped.

The result is validated by loading the JSON afterwards, so a bad repair
fails loudly instead of silently producing a wrong file.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent / "content"

#: Matches one string field per line: key, opening quote, value, closing
#: quote, optional trailing comma. The value group is GREEDY so the closing
#: quote captured is the LAST one on the line - which is the real delimiter.
_FIELD_RE = re.compile(
    r'^(\s*"(?P<key>term|answer|code|tags)":\s*")(?P<value>.*)(?P<close>")(?P<comma>,?)\s*$'
)

#: A double quote that is NOT already escaped.
_RAW_QUOTE_RE = re.compile(r'(?<!\\)"')


def repair_text(raw: str) -> str:
    """Escape raw double quotes inside the string fields of each line."""
    lines = raw.split("\n")
    repaired: list[str] = []
    for line in lines:
        match = _FIELD_RE.match(line)
        if match is None:
            repaired.append(line)
            continue
        value = match.group("value")
        fixed = _RAW_QUOTE_RE.sub(r'\\"', value)
        rebuilt = f'{match.group(1)}{fixed}{match.group("close")}{match.group("comma")}'
        repaired.append(rebuilt)
    return "\n".join(repaired)


def repair_file(path: Path) -> tuple[bool, str]:
    """Try to load the file; if it fails, repair raw quotes and retry."""
    raw = path.read_text(encoding="utf-8")

    try:
        json.loads(raw)
        return True, "already valid"
    except json.JSONDecodeError as exc:
        first_error = exc

    repaired = repair_text(raw)
    try:
        json.loads(repaired)
    except json.JSONDecodeError as exc:
        return False, f"repair failed: {exc} (original error at line {first_error.lineno})"

    path.write_text(repaired, encoding="utf-8")
    return True, f"repaired (original error at line {first_error.lineno})"


def main() -> int:
    failures = 0
    for path in sorted(CONTENT_DIR.glob("*.json")):
        ok, message = repair_file(path)
        status = "OK  " if ok else "FAIL"
        print(f"{status} {path.name}: {message}")
        if not ok:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
