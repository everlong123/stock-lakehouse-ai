"""Check the GOLD layer (the layer the charts actually read) for calendar defects.

The charts read Gold via MarketService.get_history(). So even if Bronze and
Silver are clean, a defect introduced by build_gold_features() will show up in
the UI. This checks the same three properties on Gold:
  - days carrying more than one bar
  - missing weekdays
  - the time-of-day stamp distribution (a symbol split across 13:30 and 14:30
    means the provider is not normalising the session open across DST)

    python3 scripts/diagnose_gold_calendar.py AAPL MSFT
"""

from __future__ import annotations

import io
import sys

import pandas as pd
from minio import Minio

ENDPOINT = "127.0.0.1:9000"
ACCESS = "minioadmin"
SECRET = "minioadmin"


def load(client: Minio, bucket: str, symbol: str) -> pd.DataFrame:
    frames = []
    for obj in client.list_objects(bucket, prefix=f"symbol={symbol}/", recursive=True):
        if not obj.object_name.endswith(".parquet"):
            continue
        try:
            resp = client.get_object(bucket, obj.object_name)
            payload = resp.read()
            resp.close(); resp.release_conn()
            df = pd.read_parquet(io.BytesIO(payload))
        except Exception:  # noqa: BLE001
            continue
        if not df.empty and "timestamp" in df.columns:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.loc[:, ~df.columns.duplicated()]


def main() -> None:
    client = Minio(ENDPOINT, access_key=ACCESS, secret_key=SECRET, secure=False)
    for sym in sys.argv[1:] or ["AAPL"]:
        df = load(client, "stock-gold", sym)
        if df.empty:
            print(f"=== {sym} GOLD: EMPTY ===\n")
            continue
        df["day"] = df["timestamp"].dt.date
        df["tod"] = df["timestamp"].dt.strftime("%H:%M")
        print(f"=== {sym} GOLD ===")
        print(f"  rows={len(df)} distinct ts={df['timestamp'].nunique()} days={df['day'].nunique()}")
        print(f"  cols: {list(df.columns)[:14]}")
        print("  by time-of-day:", dict(list(df["tod"].value_counts().head(8).items())))
        counts = df["day"].value_counts()
        multi = counts[counts > 1]
        print(f"  days with >1 bar: {len(multi)}")
        for d in list(multi.index)[:6]:
            sub = df[df["day"] == d]
            parts = [f"{r['timestamp']:%H:%M}={r['close']:.2f}" for _, r in sub.iterrows()]
            print(f"    {d}: " + "  ".join(parts))
        days = sorted(df["day"].unique())
        present = set(days)
        missing = [d for d in pd.date_range(days[0], days[-1], freq="D").date
                   if d not in present and d.weekday() < 5]
        print(f"  span {days[0]}..{days[-1]} missing weekdays={len(missing)}")
        if missing:
            runs = []
            run = [missing[0]]
            for d in missing[1:]:
                if (d - run[-1]).days == 1:
                    run.append(d)
                else:
                    runs.append(run); run = [d]
            runs.append(run)
            for r in runs[:8]:
                print(f"    missing {r[0]} .. {r[-1]} ({len(r)} weekdays)")
        print()


if __name__ == "__main__":
    main()
