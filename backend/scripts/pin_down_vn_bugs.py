"""Separate real corruption from a bad threshold, and pin down the VN bugs.

Correction to an earlier measurement: the '134,575 corrupt rows' figure came
from a 'timestamp < 2020' cutoff. That cutoff is WRONG - the US series
legitimately starts in 2016, so rows from 2016-2019 are valid history, not
corruption. A real daily series cannot contain a bar from 1970 though.

This uses a defensible cutoff (before 2010, i.e. outside any possible lookback
window) and then focuses on the VN symbols, where the symptoms are unambiguous:
  * vn_ws rows with 1970 timestamps, while vn_rest rows on the SAME symbol
    have correct 2026 timestamps and correct VND prices,
  * vn_ws prices that look like the correct VND price divided by 1000.

Comparing vn_ws against vn_rest for the same symbol on the same day answers
both questions at once.
"""

import sys

sys.path.insert(0, ".")

import pandas as pd

from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend

storage = MinioStorageBackend()

HARD_CORRUPT = pd.Timestamp("2010-01-01", tz="UTC")

for sym in sys.argv[1:] or ["VCB", "FPT", "VNM", "HPG"]:
    objs = [o for o in storage.list_objects("bronze", symbol_prefix(sym)) if o.endswith(".parquet")]
    frames = []
    for o in objs:
        try:
            df = storage.read_parquet("bronze", o)
        except Exception:
            continue
        if not df.empty and "timestamp" in df.columns:
            frames.append(df)
    if not frames:
        print(f"{sym}: no data\n")
        continue

    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.loc[:, ~df.columns.duplicated()].drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

    corrupt = df[df["timestamp"] < HARD_CORRUPT]
    ws = df[df["source"] == "vn_ws"]
    rest = df[df["source"] == "vn_rest"]

    print(f"=== {sym} ===")
    print(f"  total={len(df)}  hard_corrupt(1970)={len(corrupt)}")
    print(f"  vn_ws rows={len(ws)}  vn_rest rows={len(rest)}")

    if len(ws):
        print(f"  vn_ws timestamp range: {ws['timestamp'].min()} .. {ws['timestamp'].max()}")
        print(f"  vn_ws close range    : {ws['close'].min():.2f} .. {ws['close'].max():.2f}")
        print(f"  vn_ws sample ts      : {list(ws['timestamp'].head(3).astype(str))}")
        print(f"  vn_ws sample close   : {list(ws['close'].head(3).round(2))}")

    if len(rest):
        print(f"  vn_rest timestamp range: {rest['timestamp'].min()} .. {rest['timestamp'].max()}")
        print(f"  vn_rest close range    : {rest['close'].min():.2f} .. {rest['close'].max():.2f}")
        print(f"  vn_rest sample ts     : {list(rest['timestamp'].head(3).astype(str))}")
        print(f"  vn_rest sample close  : {list(rest['close'].head(3).round(2))}")

        # Direct price comparison on the same symbol.
        if len(ws):
            ws_day = ws["timestamp"].dt.date.mode().iloc[0]
            same = rest[rest["timestamp"].dt.date == ws_day]
            if len(same):
                w = ws[ws["timestamp"].dt.date == ws_day]
                print(f"  >> same day {ws_day}: vn_ws close~{w['close'].mean():.2f}  "
                      f"vn_rest close~{same['close'].mean():.2f}  "
                      f"ratio={same['close'].mean()/w['close'].mean():.2f}")

    # Hypothesis test: is the 1970 timestamp a units bug on the epoch field?
    if len(corrupt):
        raw_epoch = corrupt["timestamp"].astype("int64") // 10**9  # seconds since epoch
        print(f"  corrupt timestamps as unix seconds: min={raw_epoch.min()} max={raw_epoch.max()}")
        for factor, label in ((1000, "seconds->ms (x1000)"), (1, "already seconds")):
            cand = pd.to_datetime(raw_epoch * factor, unit="s", utc=True, errors="coerce")
            plausible = cand[(cand > pd.Timestamp("2024-01-01", tz="UTC")) & (cand < pd.Timestamp("2027-01-01", tz="UTC"))]
            print(f"    x{factor:<5d} ({label}): plausible-in-2024..2026 = {len(plausible)}/{len(cand)}")
            if len(plausible):
                print(f"      range: {plausible.min()} .. {plausible.max()}")
    print()
