"""Standalone Silver-layer calendar/source diagnosis.

Deliberately avoids importing the app package: the host's WSL python has no
pydantic, and the Windows side currently cannot reach MinIO through the
localhost forwarding path. This talks to MinIO over the WSL bridge IP
directly, with the minio client only.

    python3 scripts/diagnose_silver_calendar.py AAPL MSFT
"""

from __future__ import annotations

import collections
import io
import sys

import pandas as pd
from minio import Minio

ENDPOINT = "127.0.0.1:9000"
ACCESS = "minioadmin"
SECRET = "minioadmin"
BUCKET = "stock-silver"


def load(client: Minio, symbol: str) -> pd.DataFrame:
    frames = []
    for obj in client.list_objects(BUCKET, prefix=f"symbol={symbol}/", recursive=True):
        if not obj.object_name.endswith(".parquet"):
            continue
        try:
            resp = client.get_object(BUCKET, obj.object_name)
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
        df = load(client, sym)
        if df.empty:
            print(f"=== {sym}: EMPTY ===\n")
            continue

        print(f"=== {sym} ===")
        print(f"  columns: {list(df.columns)}")
        print(f"  rows={len(df)} distinct ts={df['timestamp'].nunique()}")

        if "source" in df.columns:
            print("  by source:")
            for src, n in df["source"].value_counts().items():
                sub = df[df["source"] == src]
                print(f"    {str(src):<22} rows={n:<6} days={sub['timestamp'].dt.date.nunique()}")

        df["day"] = df["timestamp"].dt.date
        df["tod"] = df["timestamp"].dt.strftime("%H:%M")
        print("  by time-of-day:")
        for tod, n in df["tod"].value_counts().head(12).items():
            print(f"    {tod}  rows={n}")

        counts = df["day"].value_counts()
        multi = counts[counts > 1]
        print(f"  days with >1 bar: {len(multi)}")
        for d in list(multi.index)[:8]:
            sub = df[df["day"] == d]
            parts = [
                f"{r['timestamp']:%H:%M}[{r.get('source','?')}]={r['close']:.2f}"
                for _, r in sub.iterrows()
            ]
            print(f"    {d}: " + "  ".join(parts))

        # Weekday gaps (excluding known US holidays would need a calendar; we
        # only report runs so a human can eyeball them).
        days = sorted(df["day"].unique())
        present = set(days)
        missing = [d for d in pd.date_range(days[0], days[-1], freq="D").date
                   if d not in present and d.weekday() < 5]
        print(f"  span {days[0]}..{days[-1]} distinct days={len(days)} missing weekdays={len(missing)}")
        print()


if __name__ == "__main__":
    main()
