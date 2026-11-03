import sys, time
sys.path.insert(0, ".")
import app.services.market_service as ms

t0 = time.time()
ms.clear_symbol_cache()
frame, layer = ms._load_symbol_frame("AAPL")
t1 = time.time()
print("COLD read %.2fs layer=%s rows=%d" % (t1 - t0, layer, len(frame)))
print(frame[["timestamp", "open", "high", "low", "close", "volume"]].head(3).to_string())
print("dtypes:", frame.dtypes.to_dict())
