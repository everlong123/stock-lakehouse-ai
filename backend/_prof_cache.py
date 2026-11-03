import time, os, sys
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")

import app.services.market_service as ms

# instrument the cache
orig_put = ms._cache_put
orig_get = ms._cache_get
def put(sym, frame, layer):
    t0=time.time(); orig_put(sym, frame, layer); print("  cache_put %s (%.2fs)" % (sym, time.time()-t0))
def get(sym):
    t0=time.time(); r = orig_get(sym); dt=time.time()-t0
    print("  cache_get %s -> %s (%.2fs)" % (sym, "HIT" if r else "MISS", dt))
    return r
ms._cache_put = put
ms._cache_get = get

from app.backtesting.engine import BacktestEngine

for i in range(3):
    print("run %d:" % i)
    t0=time.time()
    r = BacktestEngine().run(symbol="AAPL", strategy_name="ma_crossover")
    print("  total: %.2fs" % (time.time()-t0))

# now time the service-level pieces
from app.lakehouse.local_storage import LocalStorageBackend
from app.backtesting.metrics import compute_metrics
print("cache size:", len(ms._cache_store))
