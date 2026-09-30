"""
Test full Lakehouse Pipeline: Bronze -> Silver -> Gold
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.silver import SilverLayer
from app.lakehouse.gold import GoldLayer
from app.core.constants import SUPPORTED_SYMBOLS

print("="*60)
print("LAKEHOUSE PIPELINE TEST")
print("="*60)

# Test symbols
test_symbols = ["AAPL", "MSFT", "NVDA"]

for symbol in test_symbols:
    print(f"\n[DATA] {symbol}")
    print("-"*40)
    
    # Bronze
    bronze = BronzeLayer()
    bronze_df = bronze.read(symbol)
    print(f"  Bronze: {len(bronze_df)} rows")
    if not bronze_df.empty:
        print(f"    {bronze_df['timestamp'].min()} -> {bronze_df['timestamp'].max()}")
    
    # Silver
    silver = SilverLayer()
    silver_df = silver.read(symbol)
    print(f"  Silver: {len(silver_df)} rows")
    
    # Gold
    gold = GoldLayer()
    gold_df = gold.read(symbol)
    print(f"  Gold: {len(gold_df)} rows")
    if not gold_df.empty:
        print(f"    Features: {len(gold_df.columns)} columns")
        print(f"    Sample: sma_20={gold_df['sma_20'].iloc[-1]:.2f}, rsi_14={gold_df['rsi_14'].iloc[-1]:.2f}")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
