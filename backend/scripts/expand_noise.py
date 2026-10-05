"""Add more Vietnamese syllables to NOISE set."""

from pathlib import Path

p = Path("app/agent/agent.py")
content = p.read_text(encoding="utf-8")

OLD = '        "CHO", "CO", "TOI", "BAN", "MINH", "EM",'
NEW = '        "CHO", "CO", "CUA", "TOI", "BAN", "MINH", "EM",\n        "DU", "LAM", "GI", "NAO", "GIA", "TANG", "GIAM", "PHIEN",'

if OLD not in content:
    print("NOT FOUND")
    raise SystemExit(1)
content = content.replace(OLD, NEW, 1)
p.write_text(content, encoding="utf-8")
print("OK expanded")