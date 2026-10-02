"""Comprehensive data demo for the lecturer.

Shows real OHLCV data, indicators, and target variables - nothing fake.

Usage:
    python scripts/demo_show_full.py
"""

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lakehouse import BronzeLayer, SilverLayer, GoldLayer, get_storage_backend

print("=" * 70)
print("STOCK LAKEHOUSE - DEMO DATA (real market data, no synthetic)")
print("=" * 70)

backend = get_storage_backend()
print(f"\n[Storage] {backend.__class__.__name__} (backend_name={backend.backend_name})")
print(f"[Buckets] stock-bronze, stock-silver, stock-gold (MinIO)")

# ── Step 1: Show what's in each layer ─────────────────────────────────────
print("\n" + "=" * 70)
print("[1] DATA INVENTORY - how many rows in each layer")
print("=" * 70)

for sym in ["AAPL", "MSFT", "NVDA", "JPM", "CAT"]:
    print(f"\n  {sym}:")
    for layer_name, layer_cls in [("BRONZE", BronzeLayer), ("SILVER", SilverLayer), ("GOLD", GoldLayer)]:
        layer = layer_cls()
        df = layer.read(sym)
        if df.empty:
            print(f"    {layer_name:6s}  (empty)")
        else:
            ts_min = df["timestamp"].min().date()
            ts_max = df["timestamp"].max().date()
            days = (df["timestamp"].max() - df["timestamp"].min()).days
            print(f"    {layer_name:6s}  rows={len(df):>5}  cols={len(df.columns):>3}  "
                  f"range=[{ts_min} -> {ts_max}]  ({days} days)")

print(f"\n  (Total 33 US equities across 8 sectors × 10 years in MinIO)")


# ── Step 2: Show raw Bronze data for VCB ──────────────────────────────────
print("\n" + "=" * 70)
print("[2] BRONZE LAYER - raw data from external API (VCB first 20 rows)")
print("=" * 70)

bronze_vcb = BronzeLayer().read("VCB")
print(f"\nColumns: {bronze_vcb.columns.tolist()}")
print(f"\nFirst 20 rows:")
print(bronze_vcb.head(20).to_string(index=False))


# ── Step 3: Show Silver quality report ─────────────────────────────────────
print("\n" + "=" * 70)
print("[3] SILVER LAYER - cleaned data with stats")
print("=" * 70)

silver_vcb = SilverLayer().read("VCB")
print(f"\nColumns: {silver_vcb.columns.tolist()}")
print(f"\nLast 10 rows:")
print(silver_vcb.tail(10)[["symbol", "timestamp", "open", "high", "low", "close", "volume"]]
    .to_string(index=False))


# ── Step 4: Show Gold features for VCB ─────────────────────────────────────
print("\n" + "=" * 70)
print("[4] GOLD LAYER - features ready for ML/DL (VCB last 10 rows)")
print("=" * 70)

gold_vcb = GoldLayer().read("VCB")
key_features = ["timestamp", "close", "volume",
                "sma_5", "sma_20", "sma_50",
                "ema_12", "ema_26",
                "rsi_14", "macd", "signal_line",
                "bb_upper", "bb_lower",
                "return_1d", "target_close_next", "target_direction_next"]

available_features = [f for f in key_features if f in gold_vcb.columns]
print(f"\nTotal columns: {len(gold_vcb.columns)}")
print(f"\nLast 10 rows ({len(available_features)} key features):")
print(gold_vcb[available_features].tail(10).to_string(index=False))


# ── Step 5: Verify source attribution (lineage) ───────────────────────────
print("\n" + "=" * 70)
print("[5] LINEAGE - which source was each symbol fetched?")
print("=" * 70)

for sym in ["AAPL", "MSFT", "VCB"]:
    try:
        line = backend.read_json("bronze", f"symbol={sym}/_lineage.json")
        print(f"\n  {sym}:")
        print(f"    layer:                {line.get('layer')}")
        print(f"    provider:             {line.get('lineage', {}).get('provider')}")
        print(f"    interval:             {line.get('lineage', {}).get('interval')}")
        print(f"    records_received:     {line.get('records_received')}")
        print(f"    records_written:      {line.get('records_written')}")
        print(f"    duplicate_count:      {line.get('duplicate_count')}")
        print(f"    partitions:           {len(line.get('partitions', []))} files (Hive-style symbol=X/year=Y/month=Z)")
        print(f"    storage_backend:      {line.get('storage_backend')}")
        print(f"    ingestion_time:       {line.get('ingestion_time')}")
    except Exception as exc:
        print(f"\n  {sym}: (no lineage file - {exc})")


# ── Step 6: Verify quality report ──────────────────────────────────────────
print("\n" + "=" * 70)
print("[6] QUALITY REPORT - VCB quality stats")
print("=" * 70)

silver_layer = SilverLayer()
try:
    quality = backend.read_json("silver", "symbol=VCB/_quality.json")
    if quality:
        print(f"\n  symbol:              {quality.get('symbol')}")
        print(f"  record_count:        {quality.get('record_count')}")
        print(f"  source_count:        {quality.get('source_count')}")
        print(f"  duplicate_count:     {quality.get('duplicate_count')}")
        print(f"  invalid_ohlc_count:  {quality.get('invalid_ohlc_count')}")
        print(f"  invalid_volume_count:{quality.get('invalid_volume_count')}")
        print(f"  missing_count:       {quality.get('missing_count')}")
        print(f"  quality_status:      {quality.get('quality_status')}")
        print(f"  engine:              {quality.get('engine')}")
        print(f"  date_range:          {str(quality.get('min_timestamp'))[:10]} -> {str(quality.get('max_timestamp'))[:10]}")
except Exception as exc:
    print(f"  (no quality file: {exc})")


print("\n" + "=" * 70)
print("END OF DEMO - all data above is REAL market data, no synthetic.")
print("=============================================")