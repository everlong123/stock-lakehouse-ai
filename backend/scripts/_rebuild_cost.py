import time, sys
sys.path.insert(0, ".")
from app.pipelines.orchestrator import transform_to_silver, build_gold_layer

for sym in ("AAPL", "ADS.DE"):
    t0 = time.time()
    transform_to_silver(sym)
    t1 = time.time()
    build_gold_layer(sym)
    t2 = time.time()
    print("%s silver=%.2fs gold=%.2fs total=%.2fs" % (sym, t1 - t0, t2 - t1, t2 - t0))
