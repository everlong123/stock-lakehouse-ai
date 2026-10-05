from pathlib import Path

p = Path("app/agent/agent.py")
content = p.read_text(encoding="utf-8")

OLD = '        "DU", "LAM", "GI", "NAO", "GIA", "TANG", "GIAM", "PHIEN",'
NEW = '        "DU", "BAO", "LAM", "GI", "NAO", "GIA", "TANG", "GIAM", "PHIEN",'

if OLD not in content:
    print("NOT FOUND")
else:
    content = content.replace(OLD, NEW, 1)
    p.write_text(content, encoding="utf-8")
    print("OK added BAO")