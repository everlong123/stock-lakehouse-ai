"""Reproduce the agent slowdown WITHOUT a server.

Hypothesis: the walk-forward validator's pure-pandas work is starved of the
GIL by the background auto-refresh threads, so it runs 50x slower than it does
on an idle process.

This script starts N threads that do the same kind of pandas/MinIO work the
refresh does (frame copies, RSI, dedupe) and times the walk-forward in the
main thread, with and without the competing load.
"""
import sys, time, threading
sys.path.insert(0, ".")
import pandas as pd

from app.backtesting.walk_forward import WalkForwardValidator
from app.services.market_service import _load_symbol_frame

stop = threading.Event()


def refresh_like_worker():
    """Mimic the refresh's hot loop: slice a wide frame, run RSI, dedupe."""
    while not stop.is_set():
        try:
            frame, _ = _load_symbol_frame("AAPL")
            if frame.empty:
                time.sleep(0.05)
                continue
            for _ in range(3):
                part = frame.head(2500).copy()
                from app.indicators.rsi import rsi
                rsi(part["close"], 14)
                part.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
        except Exception:
            time.sleep(0.05)


def time_wf(label):
    t0 = time.time()
    res = WalkForwardValidator().run(symbol="AAPL", strategy_name="rsi_strategy")
    dt = time.time() - t0
    print("%-24s walk-forward %.2fs (windows=%d)" % (label, dt, res["summary"]["total_windows"]))
    return dt


print("=== idle ===")
idle = time_wf("idle")

workers = []
for _ in range(8):
    t = threading.Thread(target=refresh_like_worker, daemon=True)
    t.start()
    workers.append(t)
time.sleep(2)
print("=== with 8 competing threads ===")
loaded = time_wf("under load")
stop.set()
for t in workers:
    t.join(timeout=3)

print()
print("RESULT: idle %.2fs -> loaded %.2fs  (%.1fx slowdown)" % (idle, loaded, loaded / idle))
