import time, sys
sys.path.insert(0, ".")
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.silver import SilverLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.parquet_manager import split_by_partition
from app.lakehouse.storage_factory import get_storage_backend

sym = "AAPL"
storage = get_storage_backend()

t0 = time.time()
keys = [k for k in storage.list_objects("gold", f"symbol={sym}/") if k.endswith(".parquet")]
print("list_objects: %.2fs (%d keys)" % (time.time() - t0, len(keys)))

t0 = time.time()
bf = BronzeLayer().read(sym)
print("bronze read: %.2fs (%d rows)" % (time.time() - t0, len(bf)))

t0 = time.time()
sf = SilverLayer().read(sym)
print("silver read: %.2fs (%d rows)" % (time.time() - t0, len(sf)))

t0 = time.time()
gf = GoldLayer().read(sym)
print("gold read: %.2fs (%d rows)" % (time.time() - t0, len(gf)))

parts = split_by_partition(gf)
t0 = time.time()
for path, group in parts.items():
    storage.write_parquet("gold", path, group)
print("gold write %d partitions: %.2fs" % (len(parts), time.time() - t0))

t0 = time.time()
for path, group in parts.items():
    storage.read_parquet("gold", path)
print("gold re-read %d partitions: %.2fs" % (len(parts), time.time() - t0))
