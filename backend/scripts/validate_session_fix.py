"""Validate the session canonicalisation against the real Bronze data.

Pulls the affected symbols straight out of MinIO and runs the same
canonicalisation the Silver layer now applies, so the fix is verified on
the rows that actually caused the chart defects.

    python3 scripts/validate_session_fix.py
"""

from __future__ import annotations

import io
import importlib.util
import sys
from pathlib import Path

import pandas as pd
from minio import Minio

# `app.lakehouse.__init__` pulls in the whole app (pydantic, settings, ...).
# The session module has no such dependencies, so it is loaded directly from
# its file to keep this script runnable in a bare interpreter.
_MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "lakehouse" / "session.py"
_spec = importlib.util.spec_from_file_location("lakehouse_session", _MODULE_PATH)
_session = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_session)
canonicalize_daily_sessions = _session.canonicalize_daily_sessions

ENDPOINT = "127.0.0.1:9000"
ACCESS = "minioadmin"
SECRET = "minioadmin"

# The symbols that showed the defects in the audit.
TARGETS = ["AAPL", "VCB", "ABX.TO", "BIDU", "BBD"]


def load(client: Minio, bucket: str, symbol: str) -> pd.DataFrame:
    keys = [
        o.object_name
        for o in client.list_objects(bucket, prefix=f"symbol={symbol}/", recursive=True)
        if o.object_name.endswith(".parquet")
    ]
    frames = []
    for name in sorted(keys):
        resp = client.get_object(bucket, name)
        payload = resp.read()
        resp.close(); resp.release_conn()
        try:
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
    for symbol in TARGETS:
        raw = load(client, "stock-bronze", symbol)
        if raw.empty:
            print(f"{symbol}: no bronze rows")
            continue
        out, report = canonicalize_daily_sessions(raw)
        dup_days = int(raw["timestamp"].dt.date.duplicated().sum())
        out_dup_days = int(out["timestamp"].dt.date.duplicated().sum())
        print(f"=== {symbol} ===")
        print(f"  bronze rows            : {len(raw)}")
        print(f"  rows per trading day   : {len(raw) / max(raw['timestamp'].dt.date.nunique(), 1):.1f} avg")
        print(f"  days with >1 row       : {dup_days}")
        print(f"  after canonicalisation  : {len(out)} rows, {out['timestamp'].dt.date.nunique()} days")
        print(f"  days still duplicated  : {out_dup_days}")
        print(f"  re-stamped rows dropped: {report['duplicate_session_rows_dropped']}")
        print(f"  intraday days aggregated: {report['intraday_days_aggregated']}")
        if not out.empty:
            last = out.iloc[-1]
            print(f"  latest bar             : {last['timestamp']} close={last['close']:.2f} "
                  f"src={last.get('source')}")
        print()


if __name__ == "__main__":
    main()
