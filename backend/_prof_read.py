import time, os, sys
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")
from app.lakehouse.gold import GoldLayer
from app.lakehouse.minio_storage import MinioStorageBackend

st = MinioStorageBackend()
t0=time.time(); keys = st.list_objects("gold", "AAPL"); print("list gold AAPL: %.1fs keys=%d" % (time.time()-t0, len(keys)))

t0=time.time()
f = GoldLayer().read("AAPL")
print("GoldLayer.read(AAPL): %.1fs rows=%d" % (time.time()-t0, len(f)))
print(f[["timestamp","close"]].head(3))
print("nulls in close:", f["close"].isna().sum())
