import time, os, sys
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")

from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.silver import SilverLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.minio_storage import MinioStorageBackend

st = MinioStorageBackend()
for layer in ("bronze","silver","gold"):
    keys = st.list_objects(layer, "symbol=AAPL/")
    pq = [k for k in keys if k.endswith(".parquet")]
    print("%s: %d objects (%d parquet)" % (layer, len(keys), len(pq)))

t0=time.time(); b = BronzeLayer().read("AAPL"); print("bronze.read: %.1fs rows=%d" % (time.time()-t0, len(b)))
t0=time.time(); s = SilverLayer().read("AAPL"); print("silver.read: %.1fs rows=%d" % (time.time()-t0, len(s)))

from app.pipelines.orchestrator import transform_to_silver, build_gold_layer
t0=time.time(); transform_to_silver("AAPL"); print("transform_to_silver: %.1fs" % (time.time()-t0))
t0=time.time(); build_gold_layer("AAPL"); print("build_gold_layer: %.1fs" % (time.time()-t0))

# how much of bronze.read is list_objects vs download?
t0=time.time(); keys = st.list_objects("bronze","symbol=AAPL/"); print("list_objects bronze: %.2fs (%d keys)" % (time.time()-t0, len(keys)))
pq = [k for k in keys if k.endswith(".parquet")]
t0=time.time()
frames=[st.read_parquet("bronze",k) for k in pq]
print("serial download of %d partitions: %.1fs" % (len(pq), time.time()-t0))
