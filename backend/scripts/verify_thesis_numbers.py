"""Cross-check the numbers quoted in the thesis against the live system.

WHAT THIS DOES
--------------
The thesis quotes numbers that a reader can verify: how many forecasts the
ledger holds, how many of them have been scored, what the mean absolute error
is, and so on. A number that is correct today but wrong tomorrow is worse
than no number at all, because nobody re-checks a figure they have already
read.

This script reads the live MySQL ledger and the live MinIO buckets, then
compares them against the figures the thesis claims. It exits non-zero when
anything disagrees, so it can gate a commit or a submission.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It never repairs a number. A mismatch means one of two things - the system
moved on (a new nightly batch scored more forecasts) or the document is
stale - and which of those it is, is a judgement a human makes after reading
the output. A script that silently rewrote the document would destroy the
very thing it is meant to protect.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pymysql

# The thesis body that ships with the project. The submission copy is
# exported from this document, so the checks run against the source.
DOC = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "HE_THONG_TOAN_DIEN_VA_GIAI_TRINH_KHOA_LUAN.md"
)
text = DOC.read_text(encoding="utf-8")


def _fmt_thousands(value: int) -> str:
    """46334 -> "46.505" (the Vietnamese thousands separator)."""
    return f"{value:,}".replace(",", ".")


def _fmt_decimal(value: float, places: int = 2) -> str:
    """335.949 -> "336,04" (comma as the decimal separator)."""
    return f"{value:.{places}f}".replace(".", ",")


try:
    conn = pymysql.connect(
        host="127.0.0.1", port=13307, user="root", password="123456", database="stock_lakehouse"
    )
except pymysql.err.OperationalError as exc:
    # The infrastructure being down is a normal state, not a script bug.
    # Say so plainly instead of dumping a stack trace, because the reader
    # needs to know what to fix, not how the exception was raised.
    print(f"Cannot reach MySQL at 127.0.0.1:13307 - {exc}")
    print("Start the infrastructure first:")
    print("  wsl -d Ubuntu-24.04 -u root -e bash -c \"cd /mnt/d/School/kltn/stock-lakehouse-ai && docker compose up -d mysql minio\"")
    print("  wsl -d Ubuntu-24.04 -u root -e bash -c \"cd /mnt/d/School/kltn/stock-lakehouse-ai && python3 backend/scripts/relay_ports.py 13307:3307 19000:9000\"")
    sys.exit(2)

cur = conn.cursor()

checks: list[tuple[str, str, str]] = []

cur.execute("select count(*) from predictions")
total = cur.fetchone()[0]
checks.append((_fmt_thousands(total), "total predictions", "46.531"))

cur.execute("select count(*) from predictions where actual_close is not null")
scored = cur.fetchone()[0]
checks.append((_fmt_thousands(scored), "scored predictions", "46.487"))

cur.execute("select count(distinct symbol) from predictions")
nsym = cur.fetchone()[0]
checks.append((str(nsym), "symbols predicted", "974"))

# The MAE the thesis quotes is the one computed over the rows that carry a
# usable reference price. Rows without one cannot form a percentage error, so
# they are excluded from the scored population, and the count of what was
# excluded is reported next to the figure rather than hidden.
cur.execute(
    "select count(*) from predictions "
    "where actual_close is not null and reference_close is not null and reference_close > 0"
)
scored_valid = cur.fetchone()[0]
checks.append((_fmt_thousands(scored_valid), "scored (valid ref)", "45.733"))

cur.execute(
    "select avg(abs_error) from predictions "
    "where actual_close is not null and reference_close is not null and reference_close > 0"
)
mae = cur.fetchone()[0]
checks.append((_fmt_decimal(mae), "MAE (scored rows)", "337,61"))

cur.execute("select avg(abs_error) from predictions where actual_close is not null")
mae_all = cur.fetchone()[0]
checks.append((_fmt_decimal(mae_all), "MAE (all scored)", "339,95"))

cur.execute(
    "select count(*) from predictions where direction_correct = 1 and actual_close is not null"
)
dir_ok = cur.fetchone()[0]
cur.execute("select count(*) from predictions where direction_correct is not null")
dir_n = cur.fetchone()[0]
da = dir_ok / dir_n if dir_n else 0.0
checks.append((f"{_fmt_decimal(da * 100)}%", "directional accuracy", "50,60%"))

cur.execute("select count(*) from agent_conversations")
nconv = cur.fetchone()[0]
checks.append((str(nconv), "agent conversations", "163"))

conn.close()

print(f"{'LIVE':<14} {'WHAT':<24} {'DOC SAYS':<16} MATCH")
print("-" * 70)
ok = True
for actual, what, doc_says in checks:
    match = actual == doc_says
    ok = ok and match
    print(f"{actual:<14} {what:<24} {doc_says:<16} {'OK' if match else 'MISMATCH'}")

# Every headline figure the thesis quotes must actually appear in the text.
# A figure that lives only in this script is a figure no reader can check.
QUOTED_FIGURES = (
    "46.531",
    "46.487",
    "45.733",
    "337,61",
    "50,60%",
    "1.002",
    "3.687",
    "603",
    "101",
    "163",
)
for number in QUOTED_FIGURES:
    present = number in text
    ok = ok and present
    print(f"{number:<14} {'present in doc':<24} {'':<16} {'OK' if present else 'MISSING'}")

# The test-run duration quoted in the thesis must match the measured value.
# Measured: 75s wall clock on the dev machine on 18/11/2026 (rounded to 75s in
# the document). Update both places together whenever the suite runtime changes
# materially.
MEASURED_RUNTIME = 75
quoted = re.search(r"chạy trong \*\*(\d+) giây\*\*", text)
if quoted:
    match = int(quoted.group(1)) == MEASURED_RUNTIME
    ok = ok and match
    print(
        f"{quoted.group(1):<14} {'test runtime (s)':<24} {str(MEASURED_RUNTIME):<16} "
        f"{'OK' if match else 'MISMATCH'}"
    )
else:
    ok = False
    print(f"{'?':<14} {'test runtime (s)':<24} {'':<16} {'MISSING'}")

print("-" * 70)
print("ALL CONSISTENT" if ok else "DISCREPANCIES FOUND")
sys.exit(0 if ok else 1)
