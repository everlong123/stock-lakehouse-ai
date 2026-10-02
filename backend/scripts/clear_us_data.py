"""Clear Bronze/Silver/Gold data for given symbols (US only here)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lakehouse.storage_factory import get_storage_backend
from app.lakehouse.minio_storage import LAYER_BUCKETS
import logging
logging.basicConfig(level=logging.WARNING)

backend = get_storage_backend()
print(f"Backend: {backend.__class__.__name__}")

ALL_US = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "AMZN",
          "META", "ADBE", "CSCO", "ORCL",
          "JPM", "BAC", "GS", "V", "MA",
          "JNJ", "PFE", "UNH", "LLY", "MRK",
          "HD", "NKE", "MCD",
          "KO", "PEP", "WMT", "PG",
          "XOM", "CVX",
          "BA", "CAT",
          "NFLX", "DIS"]
print(f"Clearing {len(ALL_US)} US symbols across bronze/silver/gold...")

total_deleted = 0
for sym in ALL_US:
    for layer in ["bronze", "silver", "gold"]:
        prefix = f"symbol={sym}/"
        objs = backend.list_objects(layer, prefix)
        bucket = LAYER_BUCKETS[layer]
        for key in objs:
            try:
                backend.client.remove_object(bucket, key)
                total_deleted += 1
            except Exception as e:
                print(f"  [FAIL] {key}: {e}")

print(f"Done. Deleted {total_deleted} objects.")