"""Smoke-test the auto-refresh service against a small symbol set."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(r"D:\School\kltn\stock-lakehouse-ai\backend")))

from app.services.auto_refresh import AutoRefreshService

svc = AutoRefreshService()
# override for smoke test: only AAPL
svc._symbols = ["AAPL"]
svc._batch_size = 5
svc._skip_if_fresh_hours = 0  # force re-fetch no matter what
print("Running smoke test for AAPL...")
summary = svc.run_once()
print("DONE:", summary)
