"""Verify MinIO silver/gold contents via Python."""
from pathlib import Path

ROOT = Path("d:/School/kltn/stock-lakehouse-ai/minio_data")

for layer in ["bronze", "silver", "gold"]:
    base = ROOT / f"stock-{layer}"
    if not base.exists():
        print(f"{layer}: directory missing")
        continue
    symbols = [d for d in base.iterdir() if d.is_dir() and d.name.startswith("symbol=")]
    print(f"=== {layer.upper()} ===")
    print(f"Total symbols: {len(symbols)}")
    if symbols:
        # Show one symbol's full structure
        sample = symbols[0]
        print(f"Sample: {sample.name}")
        for sub in sample.iterdir():
            if sub.is_dir():
                files = list(sub.rglob("*.parquet"))
                print(f"  {sub.name}: {len(files)} parquet files")
            else:
                print(f"  {sub.name} (file)")
    # Print all symbol names
    all_syms = sorted([s.name.replace("symbol=", "") for s in symbols])
    print(f"Symbols: {all_syms}")
    print()