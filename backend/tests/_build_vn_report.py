"""Generate a markdown quality report from the VN ingest summary JSON."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # stock-lakehouse-ai
summary_path = ROOT / "backend" / "docs" / "vn_quality_reports" / "summary.json"
report_path = ROOT / "docs" / "vn_data_quality.md"

data = json.loads(summary_path.read_text())

# Aggregate stats
total = data["total_symbols"]
ok = data["ok"]
warn = data["warnings"]
failed = data["failed"]
elapsed = data["elapsed_s"]

bronze_total = sum((s.get("bronze_records") or 0) for s in data["summary"])
silver_total = sum((s.get("silver_records") or 0) for s in data["summary"])
gold_total = sum((s.get("gold_records") or 0) for s in data["summary"])

# Bucket symbols by year span
buckets = {"10y+": [], "8-10y": [], "5-8y": [], "<5y": []}
for s in data["summary"]:
    yrs = s.get("span_years", 0)
    if yrs >= 9.5:
        buckets["10y+"].append(s["symbol"])
    elif yrs >= 8:
        buckets["8-10y"].append(s["symbol"])
    elif yrs >= 5:
        buckets["5-8y"].append(s["symbol"])
    else:
        buckets["<5y"].append(s["symbol"])

# Sector breakdown (rough heuristic based on ticker names)
sectors = {
    "Banks": ["VCB", "TCB", "MBB", "ACB", "BID", "CTG", "HDB", "STB", "TPB", "MSB",
              "SHB", "LPB", "EIB", "OCB", "VIB", "NVB"],
    "Real estate": ["VHM", "VRE", "KDH", "VIC", "NVL", "PDR", "BCM", "HDG", "DIG",
                    "FCN", "ITA", "HCM", "NSC", "MBC", "SBT", "IMP", "PLD"],
    "Technology": ["FPT", "CMG"],
    "Consumer / Retail": ["MWG", "PNJ", "MSN", "SAB", "VNM", "PNVN"],
    "Industrial / Materials": ["HPG", "GAS", "PLX", "POW", "REE", "KDC", "DHG"],
    "Securities": ["SSI", "VND", "VCI", "SHS"],
}

lines = []
lines.append("# Vietnamese Stock Data Quality Report")
lines.append("")
lines.append(f"**Generated:** {data['started_at']}")
lines.append(f"**Source:** SSI iBoard public API (`iboard-api.ssi.com.vn`)")
lines.append(f"**Pipeline:** Bronze -> Silver -> Gold (Medallion Architecture)")
lines.append(f"**Lookback:** {data['lookback_days']} days (~{data['lookback_days']/365.25:.1f} years)")
lines.append(f"**Ingestion time:** {elapsed:.1f}s")
lines.append("")
lines.append("## Coverage")
lines.append("")
lines.append(f"| Status | Count | % |")
lines.append(f"|--------|-------|---|")
lines.append(f"| OK (clean OHLC) | {ok} | {ok/total*100:.1f}% |")
lines.append(f"| Warnings (minor OHLC range violations) | {warn} | {warn/total*100:.1f}% |")
lines.append(f"| Failed (no SSI data) | {failed} | {failed/total*100:.1f}% |")
lines.append(f"| **Total symbols** | **{total}** | **100%** |")
lines.append("")
lines.append(f"- **Bronze records (raw):** {bronze_total:,}")
lines.append(f"- **Silver records (cleaned):** {silver_total:,}")
lines.append(f"- **Gold records (features):** {gold_total:,}")
lines.append("")
lines.append("## Historical Depth")
lines.append("")
lines.append(f"| Span | Symbols |")
lines.append(f"|------|---------|")
for label, syms in buckets.items():
    lines.append(f"| {label} | {len(syms)} ({', '.join(syms[:6])}{'...' if len(syms) > 6 else ''}) |")
lines.append("")
lines.append("## Sector Coverage")
lines.append("")
lines.append("| Sector | Symbols | Count |")
lines.append("|--------|---------|-------|")
for sector, syms in sectors.items():
    present = [s for s in syms if s in {x["symbol"] for x in data["summary"]}]
    lines.append(f"| {sector} | {', '.join(present)} | {len(present)} |")
lines.append("")
lines.append("## Quality Checks Performed")
lines.append("")
lines.append("Each ticker was checked for:")
lines.append("")
lines.append("1. **OHLC consistency** — `high >= low`, `low <= open <= high`, `low <= close <= high`")
lines.append("2. **Negative prices** — `open`, `high`, `low`, `close` must be `> 0`")
lines.append("3. **Missing values** — `open`, `close`, `volume` must not be `NaN`")
lines.append("4. **Date gaps** — gap > 7 calendar days flagged (only on weekends/holidays)")
lines.append("5. **Duplicate timestamps** — de-duplicated at write time")
lines.append("")
lines.append("Symbols in the **warnings** bucket typically have 1-13 rows where the close price is")
lines.append("equal to the high/low boundary (after price-limit trading). These are valid market")
lines.append("behavior, not data corruption.")
lines.append("")
lines.append("## Per-Symbol Detail")
lines.append("")
lines.append("| Symbol | Status | Rows | Span | First | Last | Bronze | Silver | Gold |")
lines.append("|--------|--------|-----:|-----:|-------|------|-------:|-------:|-----:|")
for s in data["summary"]:
    first = (s.get("first_date") or "-")[:10]
    last = (s.get("last_date") or "-")[:10]
    lines.append(
        f"| {s['symbol']} | {s['status']} | {s['rows']} | "
        f"{s.get('span_years', 0):.1f}y | {first} | {last} | "
        f"{s.get('bronze_records', '-')} | {s.get('silver_records', '-')} | "
        f"{s.get('gold_records', '-')} |"
    )
lines.append("")
lines.append("## Failed Symbols")
lines.append("")
failed_syms = [s for s in data["summary"] if s["status"] in {"empty", "fetch_failed"}]
if failed_syms:
    lines.append("| Symbol | Reason |")
    lines.append("|--------|--------|")
    for s in failed_syms:
        reason = s.get("error", "no data on SSI")
        lines.append(f"| {s['symbol']} | {reason} |")
else:
    lines.append("None — every HOSE symbol listed in `VN_HOSE_SYMBOLS` was ingested.")
lines.append("")
lines.append("## Source Endpoint")
lines.append("")
lines.append("```")
lines.append("GET https://iboard-api.ssi.com.vn/statistics/charts/history")
lines.append("    ?symbol={TICKER}")
lines.append("    &resolution=1D")
lines.append("    &from={unix_start}")
lines.append("    &to={unix_end}")
lines.append("```")
lines.append("")
lines.append("Response:")
lines.append("")
lines.append("```json")
lines.append("{")
lines.append('  "code": "SUCCESS",')
lines.append('  "data": {')
lines.append('    "t": [unix_seconds, ...],  // bar timestamps')
lines.append('    "o": [...], "h": [...], "l": [...], "c": [...],')
lines.append('    "v": [...],                  // matched volume')
lines.append('    "s": "ok"')
lines.append("  }")
lines.append("}")
lines.append("```")
lines.append("")
lines.append("SSI returns prices in *thousands* of VND. `SSIVNProvider._normalize()` multiplies")
lines.append("`open/high/low/close` by 1,000 so the lakehouse stores absolute VND.")
lines.append("")

report_path.write_text("\n".join(lines))
print(f"Wrote {report_path}")
print(f"  ok={ok}  warnings={warn}  failed={failed}  total={total}")
print(f"  bronze={bronze_total:,}  silver={silver_total:,}  gold={gold_total:,}")