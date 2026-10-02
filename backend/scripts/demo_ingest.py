"""Demo script: ingest 3 real symbols into MinIO."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipelines import run_symbol_pipeline
import time

symbols = ["AAPL", "MSFT", "VCB"]
for sym in symbols:
    t0 = time.time()
    try:
        # Để source_name=None → multi_source failover (yfinance → alpha_vantage → web_scraper → finnhub)
        r = run_symbol_pipeline(sym, interval="1d", source_name=None)
        status = r["status"]
        recs = r["records_processed"]
        qual = r["quality"]["quality_status"]
        elapsed = round(time.time() - t0, 1)
        print(f"[OK] {sym}: status={status} records={recs} quality={qual} time={elapsed}s")
    except Exception as exc:
        elapsed = round(time.time() - t0, 1)
        print(f"[FAIL] {sym}: {type(exc).__name__}: {str(exc)[:200]} ({elapsed}s)")