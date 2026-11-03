"""Test whether the MinIO urllib3 pool (maxsize=64, block=True) hangs under load."""
import sys, time, threading
sys.path.insert(0, ".")
import pandas as pd
from app.lakehouse.storage_factory import get_storage_backend

storage = get_storage_backend()
frame = pd.DataFrame({
    "symbol": ["PROBE"], "timestamp": pd.to_datetime(["2020-01-01"], utc=True),
    "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0],
    "adj_close": [1.0], "volume": [1.0], "source": ["probe"],
    "ingestion_time": pd.to_datetime(["2020-01-01"], utc=True),
})

stop = threading.Event()
def hog():
    while not stop.is_set():
        try:
            storage.write_parquet("bronze", "_probe/hog.parquet", frame)
        except Exception:
            pass

hogs = [threading.Thread(target=hog, daemon=True) for _ in range(80)]
for h in hogs:
    h.start()
time.sleep(3)

t0 = time.time()
try:
    storage.read_parquet("bronze", "_probe/hog.parquet")
    print("GET after saturation took %.2fs" % (time.time() - t0))
except Exception as exc:
    print("GET failed after %.2fs: %s" % (time.time() - t0, exc))
stop.set()
for h in hogs:
    h.join(timeout=2)
print("done")
