"""Final diagnostic before the fix: where do the duplicate daily bars come from?

The universe audit found 23,464 rows beyond one-per-trading-day across 486
symbols, and 9 different time-of-day stamps in a single symbol's series. This
script answers:

  1. Which (source, time-of-day) combinations produce the extra rows?
  2. Would the existing `dedupe_same_bars` rule collapse them, or does it
     fail because the payloads differ?
  3. Do VN symbols (which legitimately carry intraday ticks) look different
     from US symbols, so a fix can treat them differently?

    python3 scripts/diagnose_duplicates.py AAPL MSFT VCB VNM
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


def load(client: Minio, bucket: str, symbol: str, newest_only: int = 6) -> pd.DataFrame:
    keys = [
        o.object_name
        for o in client.list_objects(bucket, prefix=f"symbol={symbol}/", recursive=True)
        if o.object_name.endswith(".parquet")
    ]
    frames = []
    for name in sorted(keys, reverse=True)[:newest_only]:
        try:
            resp = client.get_object(bucket, name)
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
        df = load(client, "stock-silver", sym)
        if df.empty:
            print(f"=== {sym}: EMPTY ===\n")
            continue
        df["day"] = df["timestamp"].dt.date
        df["tod"] = df["timestamp"].dt.strftime("%H:%M")

        print(f"=== {sym} ===")
        print(f"  rows={len(df)} days={df['day'].nunique()}")

        combo = collections.Counter(
            f"{r.get('source','?')}@{r['tod']}" for _, r in df.iterrows()
        )
        print("  (source @ time-of-day):")
        for k, n in combo.most_common(10):
            print(f"    {k:<28} {n}")

        counts = df["day"].value_counts()
        dup_days = counts[counts > 1]
        print(f"  days with >1 bar: {len(dup_days)}  extra rows: {int((dup_days - 1).sum())}")

        # Do the duplicate rows carry the SAME price payload?
        same_payload = 0
        diff_payload = 0
        for d in list(dup_days.index)[:200]:
            sub = df[df["day"] == d]
            prices = sub[["open", "high", "low", "close"]].round(6).drop_duplicates()
            if len(prices) == 1:
                same_payload += 1
            else:
                diff_payload += 1
        print(f"  dup days with IDENTICAL payload: {same_payload}, with DIFFERING payload: {diff_payload}")

        for d in list(dup_days.index)[:4]:
            sub = df[df["day"] == d]
            parts = [
                f"{r['timestamp']:%H:%M}[{r.get('source','?')}]"
                f"o={r['open']:.2f} h={r['high']:.2f} l={r['low']:.2f} c={r['close']:.2f} v={r['volume']}"
                for _, r in sub.iterrows()
            ]
            print(f"    {d}:")
            for p in parts:
                print(f"        {p}")
        print()


if __name__ == "__main__":
    main()
