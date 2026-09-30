"""Print VN ingestion summary as a readable table."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
summary_path = ROOT / "docs" / "vn_quality_reports" / "summary.json"
data = json.loads(summary_path.read_text())

print("VN INGESTION SUMMARY")
print("=" * 100)
print(
    f"Total: {data['total_symbols']} | OK: {data['ok']} | "
    f"warnings: {data['warnings']} | failed: {data['failed']}"
)
print(f"Elapsed: {data['elapsed_s']}s")
print("=" * 100)
header = (
    f"{'Symbol':<7s} {'Status':<11s} {'Rows':>6s} {'Years':>6s} "
    f"{'First':>12s} {'Last':>12s} {'Bronze':>7s} {'Silver':>7s} {'Gold':>5s}"
)
print(header)
print("-" * 100)

total_rows = 0
ok_count = 0
warn_count = 0
fail_count = 0

for s in data["summary"]:
    issues = ",".join(s.get("issues", [])[:2]) if s.get("issues") else ""
    first = (s.get("first_date") or "-")[:10]
    last = (s.get("last_date") or "-")[:10]
    years = s.get("span_years", 0)
    bronze = s.get("bronze_records", "-")
    silver = s.get("silver_records", "-")
    gold = s.get("gold_records", "-")

    line = (
        f"{s['symbol']:<7s} {s['status']:<11s} {s['rows']:>6} {years:>6.1f} "
        f"{first:>12s} {last:>12s} {str(bronze):>7s} {str(silver):>7s} {str(gold):>5s}"
    )
    if issues:
        line += f"  [{issues}]"
    print(line)
    total_rows += s["rows"]
    if s["status"] == "ok":
        ok_count += 1
    elif s["status"] == "warnings":
        warn_count += 1
    else:
        fail_count += 1

print("=" * 100)
print(
    f"Totals: ok={ok_count} warnings={warn_count} failed={fail_count}  "
    f"bronze_rows={total_rows}"
)
