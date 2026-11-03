"""Show exactly what the multi-bar days on VN symbols contain, post-fix.

VCB and FPT now report zero same-bar rows, but each still has 5 days with
more than one bar. Those could be legitimate (a VN symbol with two sessions,
or a partial extra bar) or leftovers the fix should have caught. This dumps
them in full so the question is answered from data rather than assumption.
"""

import sys

sys.path.insert(0, ".")

import pandas as pd

from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend

storage = MinioStorageBackend()

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
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.loc[:, ~df.columns.duplicated()].drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df["day"] = df["timestamp"].dt.date
    df["tod"] = df["timestamp"].dt.strftime("%H:%M")

    per_day = df.groupby("day").size()
    multi = per_day[per_day > 1]
    print(f"=== {sym}: rows={len(df)} days={df['day'].nunique()} multi_bar_days={len(multi)} sizes={multi.tolist()} ===")

    cols = [c for c in ("timestamp", "tod", "open", "high", "low", "close", "volume", "source") if c in df.columns]
    for day in multi.index:
        g = df[df["day"] == day].sort_values("timestamp")
        print(f"  --- {day} ---")
        for _, r in g.iterrows():
            print(f"    {r['timestamp']} tod={r['tod']} o={r.get('open', float('nan')):.2f} "
                  f"c={r.get('close', float('nan')):.2f} v={r.get('volume', float('nan')):.0f} src={r.get('source', '?')}")
    print()

    print(f"  time-of-day histogram: {df['tod'].value_counts().to_dict()}")
    print()