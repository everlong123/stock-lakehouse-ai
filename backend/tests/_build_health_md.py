"""Build markdown report from system_health_report.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # stock-lakehouse-ai
json_path = ROOT / "backend" / "docs" / "system_health_report.json"
md_path = ROOT / "docs" / "system_health.md"

data = json.loads(json_path.read_text(encoding="utf-8"))
summary = data["summary"]
checks = data["checks"]

lines = []
lines.append("# Lakehouse System Health Report")
lines.append("")
lines.append(f"**Generated:** {data['generated_at']}")
lines.append("")
lines.append("## Summary")
lines.append("")
lines.append(f"| Pass | Warn | Fail | Total |")
lines.append(f"|------|------|------|-------|")
lines.append(f"| {summary['pass']} | {summary['warn']} | {summary['fail']} | {summary['total']} |")
lines.append("")
lines.append("## Detailed Checks")
lines.append("")
lines.append("| Category | Status | Detail |")
lines.append("|----------|--------|--------|")

for c in checks:
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(c["status"], "?")
    lines.append(f"| `{c['category']}` | {icon} {c['status']} | {c['detail']} |")

lines.append("")
lines.append("## Coverage")
lines.append("")
# Group by category prefix
groups: dict[str, list[dict]] = {}
for c in checks:
    prefix = c["category"].split(" ")[0]
    groups.setdefault(prefix, []).append(c)

for prefix, items in sorted(groups.items()):
    lines.append(f"### {prefix}")
    lines.append("")
    for c in items:
        icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(c["status"], "?")
        lines.append(f"- {icon} **{c['category']}** — {c['detail']}")
    lines.append("")

lines.append("---")
lines.append("")
lines.append("Re-run with: `python backend/tests/_system_audit.py`")
lines.append("")

md_path.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {md_path}")