"""Prove the 13:30 / 14:30 split is a DST problem, and quantify it.

Yahoo's chart API stamps a daily bar at the exchange's session OPEN expressed
in UTC. The NYSE opens at 09:30 America/New_York, so the UTC stamp is:

    EST (UTC-5)  ->  14:30 UTC
    EDT (UTC-4)  ->  13:30 UTC

A series that keeps BOTH stamps is not continuous in time: consecutive bars
jump by 24h across a DST boundary and by 23h in the other direction. Every
downstream time-based calculation (returns over a rolling window, ATR, an
expiry count, a "last N sessions" slice) is then off by an hour at the seam.

This script maps each bar to its year and prints the stamp used, which makes
the pattern obvious: one stamp per calendar year, flipping at the DST
boundaries.

    python3 scripts/diagnose_dst_stamps.py AAPL
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
            print(f"=== {sym}: EMPTY ===\n")
            continue
        df["day"] = df["timestamp"].dt.date
        df["tod"] = df["timestamp"].dt.strftime("%H:%M")
        df["year"] = df["timestamp"].dt.year

        print(f"=== {sym}: session-open stamp per year ===")
        for year, g in df.groupby("year"):
            stamps = dict(g["tod"].value_counts().head(3).items())
            first = g["day"].min()
            last = g["day"].max()
            print(f"  {year}: {stamps}   ({first} .. {last})")

        # Within-year continuity: how often do consecutive bars differ by
        # something other than 1 calendar day?
        s = df.sort_values("timestamp")["timestamp"].reset_index(drop=True)
        gaps = s.diff().dt.total_seconds() / 86400.0
        odd = gaps[(gaps > 1.5) & (gaps < 2.5)]
        big = gaps[gaps > 2.5]
        print(f"  consecutive-bar gaps: ~2 days (DST seam): {len(odd)}   >2.5 days: {len(big)}")
        if len(odd):
            idx = gaps[(gaps > 1.5) & (gaps < 2.5)].index[:5]
            for i in idx:
                print(f"    {s[i-1].date()} {s[i-1]:%H:%M} -> {s[i].date()} {s[i]:%H:%M}  gap={gaps[i]:.3f}d")
        if len(big):
            idx = gaps[gaps > 2.5].index[:5]
            for i in idx:
                print(f"    {s[i-1].date()} {s[i-1]:%H:%M} -> {s[i].date()} {s[i]:%H:%M}  gap={gaps[i]:.3f}d")
        print()


if __name__ == "__main__":
    main()
