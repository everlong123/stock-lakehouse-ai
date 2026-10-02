"""Ingest VCB from SSI for many years of history."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipelines import run_symbol_pipeline
import time

t0 = time.time()
print("Ingesting VCB from SSI provider...")
try:
    r = run_symbol_pipeline("VCB", interval="1d", source_name="ssi_vn")
    elapsed = round(time.time() - t0, 1)
    print(f"[OK] VCB: status={r['status']} records={r['records_processed']} "
          f"quality={r['quality']['quality_status']} time={elapsed}s")
except Exception as exc:
    elapsed = round(time.time() - t0, 1)
    print(f"[FAIL] VCB: {type(exc).__name__}: {str(exc)[:200]} ({elapsed}s)")