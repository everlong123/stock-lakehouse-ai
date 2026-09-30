"""Verify all VN symbols through MinIO storage backend."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.lakehouse import BronzeLayer, GoldLayer, SilverLayer

bronze = BronzeLayer()
silver = SilverLayer()
gold = GoldLayer()

print(f"{'Symbol':<8s} {'Bronze':>8s} {'Silver':>8s} {'Gold':>6s}")
print("-" * 40)

vn_symbols = ["VCB", "TCB", "MBB", "FPT", "VNM", "HPG", "VIC", "SSI", "MWG", "BID",
              "VHM", "VRE", "ACB", "CTG", "HDB", "STB", "TPB", "MSB", "SHB", "LPB",
              "EIB", "OCB", "VIB", "NVB", "KDH", "NVL", "PDR", "BCM", "HDG", "DIG",
              "FCN", "ITA", "HCM", "NSC", "MBC", "SBT", "IMP", "PLD", "CMG", "PNJ",
              "MSN", "SAB", "PNVN", "GAS", "PLX", "POW", "REE", "KDC", "DHG", "VND",
              "VCI", "SHS"]

total_bronze = total_silver = total_gold = 0
for sym in vn_symbols:
    b = bronze.record_count(sym)
    s = silver.record_count(sym)
    g = gold.record_count(sym)
    total_bronze += b
    total_silver += s
    total_gold += g
    if b or s or g:
        print(f"{sym:<8s} {b:>8} {s:>8} {g:>6}")

print("-" * 40)
print(f"{'TOTAL':<8s} {total_bronze:>8} {total_silver:>8} {total_gold:>6}")