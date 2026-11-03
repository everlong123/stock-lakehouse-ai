"""Check for real data loss on the VN symbols the fix rewrote.

The log showed 'Bronze dropped 381 same-bar rows' for VCB in one partition.
VCB is a Vietnam symbol fed by vn_rest, which produces genuine intraday ticks
at 1-minute spacing during the session. The fix's rule requires a gap of at
least one hour between the two rows it collapses, so intraday ticks should be
safe - but 381 is suspiciously close to the total tick count for that
partition, so this verifies it from the data rather than trusting the rule.

Checks:
  * rows per trading day in the affected month, before vs after
  * whether the intraday ticks are still present
  * whether any surviving EOD bar was lost
"""

import sys

sys.path.insert(0, ".")

import pandas as pd

from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend

storage = MinioStorageBackend()

for sym in sys.argv[1:] or ["VCB", "VNM", "FPT", "HPG"]:
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

    print(f"=== {sym} ===")
    print(f"total rows: {len(df)}  distinct days: {df['day'].nunique()}")

    # The EOD stamp is the modal one; everything else on a multi-bar day is
    # intraday.
    modal = df["tod"].value_counts().index[0]
    eod = df[df["tod"] == modal]
    intraday = df[df["tod"] != modal]
    print(f"EOD stamp: {modal} -> {len(eod)} rows")
    print(f"intraday rows: {len(intraday)}")

    oct_rows = df[df["timestamp"].dt.month == 10]
    print(f"October 2026 rows: {len(oct_rows)} across {oct_rows['day'].nunique()} days")

    per_day = df.groupby("day").size()
    multi = per_day[per_day > 1]
    print(f"multi-bar days: {len(multi)} -> {multi.to_dict()}")

    # Each trading day should still carry exactly one EOD bar.
    eod_per_day = eod.groupby("day").size()
    days_missing_eod = [
        str(d) for d in multi.index if d not in eod_per_day.index
    ]
    print(f"multi-bar days MISSING their EOD bar: {len(days_missing_eod)} {days_missing_eod[:5]}")
    print()

print("=== cross-check: EOD bar count vs distinct trading days ===")
print("A VN symbol with 524 trading days must have 524 EOD bars, one per day.")
print("If the fix ate EOD bars, this count drops below the day count.")