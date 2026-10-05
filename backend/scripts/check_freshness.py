"""Check AAPL data freshness in MinIO bronze layer."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(r"D:\School\kltn\stock-lakehouse-ai\backend")))

import re
import io
import urllib3
import pandas as pd
from minio import Minio
from app.core.config import settings

http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=2, read=120))
m = Minio(
    settings.minio_endpoint,
    settings.minio_access_key,
    settings.minio_secret_key,
    secure=False,
    http_client=http,
)

# Sample AAPL bronze - find latest partition
objs = list(m.list_objects("stock-bronze", prefix="symbol=AAPL", recursive=True))
print(f"AAPL bronze files: {len(objs)}")

def keyf(o):
    p = o.object_name
    y = re.search(r"year=(\d+)", p)
    mo = re.search(r"month=(\d+)", p)
    return (int(y.group(1)) if y else 0, int(mo.group(1)) if mo else 0)

objs.sort(key=keyf)
for o in objs[-5:]:
    print(" ", o.object_name)
print("---")
# Now sample read latest month parquet
latest = objs[-1]
resp = m.get_object("stock-bronze", latest.object_name)
df = pd.read_parquet(io.BytesIO(resp.read()))
resp.close()
resp.release_conn()
ts = df["timestamp"]
print(f"  rows={len(df)}, range={ts.min()} -> {ts.max()}")
last = df.iloc[-1]
print(f"  latest close={last['close']}")
if "source" in df.columns:
    print(f"  source={last['source']}")

# Also check gold latest for AAPL
print("\n--- GOLD layer AAPL ---")
objs2 = list(m.list_objects("stock-gold", prefix="symbol=AAPL", recursive=True))
print(f"AAPL gold files: {len(objs2)}")
if objs2:
    objs2.sort(key=keyf)
    latest2 = objs2[-1]
    resp = m.get_object("stock-gold", latest2.object_name)
    df2 = pd.read_parquet(io.BytesIO(resp.read()))
    resp.close()
    resp.release_conn()
    ts2 = df2["timestamp"]
    print(f"  gold rows={len(df2)}, range={ts2.min()} -> {ts2.max()}")
