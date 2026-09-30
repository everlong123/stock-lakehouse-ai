"""Check the 2 NaN rows in VCB Bronze."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.lakehouse import BronzeLayer

bronze = BronzeLayer()
df = bronze.read("VCB")
print("Bronze VCB total:", len(df))
nan_rows = df[df["open"].isna()]
print(f"NaN rows: {len(nan_rows)}")
print(nan_rows.to_string())