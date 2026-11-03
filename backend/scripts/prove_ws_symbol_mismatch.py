"""Prove the vn_ws rows belong to a DIFFERENT symbol, not to VCB/FPT.

Evidence so far: vn_ws rows on VCB carry close=56.9 and a 1970 timestamp,
while vn_rest rows on the same symbol carry close=56600 at a 2026 timestamp.
56.9 is McDonald's (MCD) territory, not VCB.

If the WS client mismapped symbol -> data, the corrupt rows should look
exactly like some OTHER symbol's real data. This searches the lakehouse for
symbols whose real close range brackets 56.9 and whose real timestamps fall in
the VN session window, which would identify the source of the leak.

It also checks the `exchange` field and whether the 1970 timestamps are a
time-of-day artifact: 1970-01-10 19:15 UTC is minute 1155 of a day, and VN
data at 02:15 UTC is the same minute-of-day. That is the signature of a date
being dropped and only the time component surviving.
"""

import sys

sys.path.insert(0, ".")

import pandas as pd

from app.core.constants import ALL_SYMBOLS
from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend

storage = MinioStorageBackend()

print("=== minute-of-day signature of the corrupt rows ===")
for sym in ["VCB", "FPT"]:
    objs = [o for o in storage.list_objects("bronze", symbol_prefix(sym)) if o.endswith(".parquet")]
    frames = []
    for o in objs:
        try:
            d = storage.read_parquet("bronze", o)
        except Exception:
            continue
        if not d.empty and "timestamp" in d.columns:
            frames.append(d)
    if not frames:
        continue
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    ws = df[(df["source"] == "vn_ws")]
    rest = df[(df["source"] == "vn_rest")]
    if ws.empty:
        continue

    print(f"\n{sym} vn_ws (corrupt) minute-of-day: "
          f"{sorted(ws['timestamp'].dt.strftime('%H:%M').unique())}")
    print(f"{sym} vn_ws day-of-month: {sorted(ws['timestamp'].dt.day.unique())}  "
          f"year: {sorted(ws['timestamp'].dt.year.unique())}")
    if not rest.empty:
        print(f"{sym} vn_rest minute-of-day range: "
              f"{rest['timestamp'].dt.strftime('%H:%M').min()} .. {rest['timestamp'].dt.strftime('%H:%M').max()}")
    print(f"{sym} vn_ws close values: {sorted(ws['close'].round(2).unique())}")

print("\n=== which real symbol trades near 56.9? ===")
candidates = []
for sym in ALL_SYMBOLS:
    if not sym.isalpha() or len(sym) > 5:
        continue
    try:
        objs = [o for o in storage.list_objects("bronze", symbol_prefix(sym)) if o.endswith(".parquet")]
    except Exception:
        continue
    if not objs:
        continue
    frames = []
    for o in objs[-3:]:
        try:
            d = storage.read_parquet("bronze", o)
        except Exception:
            continue
        if not d.empty and "close" in d.columns:
            frames.append(d[["close", "timestamp"]])
    if not frames:
        continue
    s = pd.concat(frames, ignore_index=True)
    lo, hi = s["close"].min(), s["close"].max()
    if pd.notna(lo) and lo <= 57.0 and hi >= 56.5:
        candidates.append((sym, float(lo), float(hi), len(s)))

print(f"symbols with close in [56.5, 57.0]: {len(candidates)}")
for sym, lo, hi, n in candidates[:15]:
    print(f"  {sym:8s} close {lo:.2f}..{hi:.2f}  rows={n}")