"""Diagnose calendar gaps and duplicate days in the Silver layer.

WHY: the charts look broken because the series is not a continuous trading
calendar. Three distinct defects show up as "random missing days":

  1. GAPS - a trade day is absent between two present days (weekend/holiday
     are legitimate absences, so only weekday gaps are defects).
  2. DUPLICATES - the same calendar day appears more than once, because two
     providers stamp the same session with different UTC times.
  3. WEEKEND BARS - a bar dated Sat/Sun, which no real market produces.

Run inside the backend container:

    docker exec stock-lakehouse-backend python scripts/diagnose_calendar_gaps.py AAPL MSFT ...
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend


def main() -> None:
    storage = MinioStorageBackend()
    symbols = sys.argv[1:] or ["AAPL", "MSFT", "NVDA"]

    for sym in symbols:
        objs = [o for o in storage.list_objects("silver", symbol_prefix(sym)) if o.endswith(".parquet")]
        frames = []
        for o in objs:
            try:
                df = storage.read_parquet("silver", o)
            except Exception:  # noqa: BLE001
                continue
            if not df.empty and "timestamp" in df.columns:
                frames.append(df)
        if not frames:
            print(f"=== {sym}: no silver data ===\n")
            continue

        df = pd.concat(frames, ignore_index=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.loc[:, ~df.columns.duplicated()]

        print(f"=== {sym} ===")
        print(f"  rows={len(df)}  raw distinct timestamps={df['timestamp'].nunique()}")

        # Duplicate exact timestamps (same instant, two providers).
        dup_ts = df["timestamp"].duplicated(keep=False)
        if dup_ts.any():
            print(f"  DUPLICATE timestamps: {int(dup_ts.sum())} rows")

        # The same calendar day stamped with different UTC times.
        df["day"] = df["timestamp"].dt.date
        day_counts = df["day"].value_counts()
        multi_day = day_counts[day_counts > 1]
        if len(multi_day):
            print(f"  DAYS WITH MULTIPLE BARS: {len(multi_day)} days, "
                  f"{int(multi_day.sum())} rows")
            for d, n in list(multi_day.items())[:5]:
                sub = df[df["day"] == d][["timestamp", "close"]]
                print(f"    {d} x{n}: "
                      + ", ".join(f"{t:%H:%M}={c:.2f}" for t, c in sub.values))

        # Weekend bars.
        dow = df["timestamp"].dt.dayofweek
        weekend = df[dow >= 5]
        if len(weekend):
            print(f"  WEEKEND BARS: {len(weekend)} rows "
                  f"({weekend['day'].nunique()} distinct days)")

        # Weekday gaps: a missing Mon-Fri between the first and last day.
        days = sorted(df["day"].unique())
        present = set(days)
        missing = []
        for d in pd.date_range(days[0], days[-1], freq="D").date:
            if d in present:
                continue
            if d.weekday() < 5:  # Mon-Fri
                missing.append(d)
        print(f"  span {days[0]} .. {days[-1]}  distinct days={len(days)}")
        if missing:
            print(f"  MISSING WEEKDAYS: {len(missing)}")
            # Group into runs.
            runs = []
            run = [missing[0]]
            for d in missing[1:]:
                if (d - run[-1]).days == 1:
                    run.append(d)
                else:
                    runs.append(run)
                    run = [d]
            runs.append(run)
            for r in runs[:10]:
                print(f"    {r[0]} .. {r[-1]}  ({len(r)} weekdays missing)")
        else:
            print("  MISSING WEEKDAYS: 0")
        print()


if __name__ == "__main__":
    main()
