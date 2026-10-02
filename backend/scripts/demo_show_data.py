"""Show what's stored in MinIO (Bronze / Silver / Gold)."""

import sys
from pathlib import Path

# Force UTF-8 output on Windows (PowerShell cp1252 can't handle Unicode)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lakehouse import BronzeLayer, SilverLayer, GoldLayer, get_storage_backend

print("=" * 70)
print("MINIO STORAGE SUMMARY")
print("=" * 70)

backend = get_storage_backend()
print(f"\nStorage backend: {backend.__class__.__name__}")
print(f"backend_name:    {backend.backend_name}")

# Read each layer for each symbol
for sym in ["AAPL", "MSFT", "VCB"]:
    print(f"\n{'─' * 60}")
    print(f"  SYMBOL: {sym}")
    print(f"{'─' * 60}")
    for layer_name, layer_cls in [("BRONZE", BronzeLayer), ("SILVER", SilverLayer), ("GOLD", GoldLayer)]:
        try:
            layer = layer_cls()
            df = layer.read(sym)
            if df.empty:
                print(f"  {layer_name:6s}  (empty)")
            else:
                ts_min = df["timestamp"].min().date()
                ts_max = df["timestamp"].max().date()
                print(f"  {layer_name:6s}  rows={len(df):5d}  cols={len(df.columns):3d}  "
                      f"date_range=[{ts_min} -> {ts_max}]")
        except Exception as exc:
            print(f"  {layer_name:6s}  ERROR: {exc}")