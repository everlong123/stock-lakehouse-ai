"""Break down Silver rows by `source` and by intraday-vs-EOD timestamp.

The calendar-gap diagnosis showed that the 96 "missing weekdays" for US
symbols are all US market holidays - legitimate. The real defect is elsewhere:

    AAPL 2026-10-13 x14: 13:30=341.27, 18:44=333.55, 18:44=333.65, ...
    MSFT 2026-10-13 x4:  13:30=543.45, 18:52=416.40, 18:52=416.40, ...

The 13:30 bar is the real EOD session (13:30 UTC = 09:30 ET). Everything at
18:44 / 18:52 / 20:00 is a second copy of a session, or a stray intraday tick,
stamped with a different UTC time. Two bars for the same trading day, with
different prices, is what makes the chart look broken.

This script attributes each row to a source and to a timestamp class so we can
see WHICH producer is injecting the duplicates.

    python scripts/diagnose_row_sources.py AAPL MSFT
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend


def classify(ts: pd.Timestamp) -> str:
    hour = ts.hour
    if ts.hour == 13 and ts.minute == 30:
        return "13:30 (US open/EOD stamp)"
    if ts.hour == 20 and ts.minute == 0:
        return "20:00 (EOD re-stamp)"
    if ts.hour == 4 and ts.minute == 0:
        return "04:00 (yfinance_eod re-stamp)"
    if 13 < hour < 21:
        return f"intraday {hour:02d}:{ts.minute:02d}"
    return f"other {hour:02d}:{ts.minute:02d}"


def main() -> None:
    storage = MinioStorageBackend()
    symbols = sys.argv[1:] or ["AAPL", "MSFT"]

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
        df["day"] = df["timestamp"].dt.date
        df["class"] = df["timestamp"].map(classify)

        print(f"=== {sym} ===")
        print(f"  columns: {list(df.columns)}")
        if "source" in df.columns:
            print("  rows by source:")
            for src, n in df["source"].value_counts().items():
                sub = df[df["source"] == src]
                days = sub["day"].nunique()
                print(f"    {str(src):<20} rows={n:<6} distinct days={days}")
        print("  rows by timestamp class:")
        for cls, n in df["class"].value_counts().items():
            print(f"    {cls:<28} rows={n}")

        # The days that carry more than one bar.
        counts = df["day"].value_counts()
        multi = counts[counts > 1]
        print(f"  days with >1 bar: {len(multi)}")
        for d in list(multi.index)[:6]:
            sub = df[df["day"] == d]
            parts = []
            for _, r in sub.iterrows():
                src = r.get("source", "?")
                parts.append(f"{r['timestamp']:%H:%M}[{src}]={r['close']:.2f}")
            print(f"    {d}: " + "  ".join(parts))
        print()


if __name__ == "__main__":
    main()
