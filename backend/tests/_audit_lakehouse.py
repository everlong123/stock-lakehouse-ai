"""Audit lakehouse: verify schema, partitions, lineage, error rates."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from app.lakehouse import BronzeLayer, SilverLayer, GoldLayer

bronze = BronzeLayer()
silver = SilverLayer()
gold = GoldLayer()

print("=" * 70)
print("LAKEHOUSE LAYER AUDIT")
print("=" * 70)

# 1. List all symbols in each layer
for layer_name, layer in [("Bronze", bronze), ("Silver", silver), ("Gold", gold)]:
    print(f"\n--- {layer_name.upper()} ---")
    try:
        # Read all records metadata
        all_records = layer.storage.read_prefix(layer.layer_name, "")
        if all_records.empty:
            print(f"  Empty")
            continue
        symbols = sorted(all_records["symbol"].unique().tolist())
        print(f"  Symbols: {len(symbols)}")
        print(f"  Total records (raw): {len(all_records)}")
        # Show schema
        print(f"  Columns: {list(all_records.columns)}")
    except Exception as exc:
        print(f"  Error: {exc}")

# 2. Pick a known-good symbol and inspect each layer
print("\n" + "=" * 70)
print("PER-SYMBOL DEEP INSPECTION (VCB)")
print("=" * 70)

for layer_name, layer in [("Bronze", bronze), ("Silver", silver), ("Gold", gold)]:
    print(f"\n--- {layer_name} ---")
    try:
        df = layer.read("VCB")
        if df.empty:
            print("  EMPTY")
            continue
        print(f"  Rows: {len(df)}")
        print(f"  Date range: {df['timestamp'].min()} -> {df['timestamp'].max()}")
        print(f"  Span: {(df['timestamp'].max() - df['timestamp'].min()).days} days")
        print(f"  Columns: {list(df.columns)}")
        print(f"  NaN counts:")
        for col in df.columns:
            n_nan = df[col].isna().sum()
            if n_nan > 0:
                print(f"    {col}: {n_nan}")
        print(f"  Sample (first 3):")
        print(df.head(3).to_string())
    except Exception as exc:
        print(f"  Error: {exc}")

# 3. Check lineage/quality metadata
print("\n" + "=" * 70)
print("METADATA FILES (Bronze _lineage.json, Silver _quality.json)")
print("=" * 70)

for layer_name, layer in [("Bronze", bronze), ("Silver", silver)]:
    try:
        prefix = f"symbol=VCB/_"
        meta_files = layer.storage.list_metadata(layer.layer_name, "symbol=VCB")
        print(f"\n{layer_name} VCB metadata:")
        for f in meta_files[:3]:
            print(f"  {f}")
            try:
                content = layer.storage.read_json(layer.layer_name, f)
                for k, v in content.items():
                    if k not in {"paths", "partitions"}:
                        print(f"    {k}: {v}")
            except Exception as exc:
                print(f"    read err: {exc}")
    except Exception as exc:
        print(f"  {layer_name} metadata error: {exc}")
