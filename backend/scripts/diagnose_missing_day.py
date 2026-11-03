"""Why are some trading days missing for some symbols but present for others?

The universe audit found 946 distinct "unexplained" missing weekdays, e.g.
2026-10-21 missing in 369 symbols but present in 533. A provider outage
cannot explain that split - the market was open and Yahoo served the bar.

This script looks at the BRONZE layer (the source of truth) around a given
date for a few affected symbols, so we can see whether the row was never
ingested or was ingested and then lost downstream.

    python3 scripts/diagnose_missing_day.py 2026-10-21
"""

from __future__ import annotations

import collections
import io
import sys
from datetime import date, timedelta

import pandas as pd
from minio import Minio

ENDPOINT = "127.0.0.1:9000"
ACCESS = "minioadmin"
SECRET = "minioadmin"


def load(client: Minio, bucket: str, symbol: str) -> pd.DataFrame:
    keys = [
        o.object_name
        for o in client.list_objects(bucket, prefix=f"symbol={symbol}/", recursive=True)
        if o.object_name.endswith(".parquet")
    ]
    frames = []
    for name in sorted(keys, reverse=True)[:4]:
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
    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2026, 10, 21)
    client = Minio(ENDPOINT, access_key=ACCESS, secret_key=SECRET, secure=False)

    symbols: set[str] = set()
    for obj in client.list_objects("stock-gold", prefix="symbol=", recursive=True):
        head = obj.object_name.split("/", 1)[0]
        if head.startswith("symbol="):
            symbols.add(head.split("=", 1)[1])

    have: list[str] = []
    lack: list[str] = []
    for sym in sorted(symbols):
        df = load(client, "stock-gold", sym)
        if df.empty:
            continue
        days = set(df["timestamp"].dt.date)
        # Only judge symbols that otherwise span the target date.
        if target - timedelta(days=5) not in days or target + timedelta(days=5) not in days:
            continue
        (have if target in days else lack).append(sym)

    print(f"target day {target} ({target.strftime('%a')})")
    print(f"  symbols spanning the date: {len(have) + len(lack)}")
    print(f"    WITH the day:    {len(have)}")
    print(f"    WITHOUT the day: {len(lack)}")
    print(f"  sample lacking: {lack[:8]}")

    # For a few lacking symbols, show the bronze rows around the target.
    for sym in lack[:4]:
        print(f"\n--- {sym} (lacks {target}) ---")
        for bucket in ("stock-bronze", "stock-silver"):
            df = load(client, bucket, sym)
            if df.empty:
                print(f"  {bucket}: EMPTY")
                continue
            df["day"] = df["timestamp"].dt.date
            window = df[(df["day"] >= target - timedelta(days=4)) & (df["day"] <= target + timedelta(days=4))]
            if window.empty:
                print(f"  {bucket}: no rows in the window either")
                continue
            parts = [
                f"{r['timestamp']:%m-%d %H:%M}[{r.get('source','?')}]c={r['close']:.2f}"
                for _, r in window.iterrows()
            ]
            print(f"  {bucket}: " + "  ".join(parts))

    # Do the symbols that HAVE the day share a common stamp?
    stamps = collections.Counter()
    for sym in have[:60]:
        df = load(client, "stock-gold", sym)
        if df.empty:
            continue
        sub = df[df["timestamp"].dt.date == target]
        for _, r in sub.iterrows():
            stamps[f"{r.get('source','?')}@{r['timestamp']:%H:%M}"] += 1
    print(f"\nstamps used by symbols that HAVE the day: {dict(stamps)}")


if __name__ == "__main__":
    main()
