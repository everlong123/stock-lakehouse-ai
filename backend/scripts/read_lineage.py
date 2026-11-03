"""Read the Bronze lineage sidecars for symbols that lost a trading day.

`BronzeLayer.append` records what it received, what it wrote and what it
rejected for the last write under `symbol=<SYM>/_lineage.json`. Comparing
that with the rows actually stored tells us whether the day was never
fetched, or fetched and then dropped.

    python3 scripts/read_lineage.py ABX.TO BBD BIDU
"""

from __future__ import annotations

import io
import json
import sys

from minio import Minio

ENDPOINT = "127.0.0.1:9000"
ACCESS = "minioadmin"
SECRET = "minioadmin"


def main() -> None:
    client = Minio(ENDPOINT, access_key=ACCESS, secret_key=SECRET, secure=False)
    for sym in sys.argv[1:] or ["ABX.TO"]:
        key = f"symbol={sym}/_lineage.json"
        try:
            resp = client.get_object("stock-bronze", key)
            payload = resp.read()
            resp.close(); resp.release_conn()
            data = json.loads(payload)
        except Exception as exc:  # noqa: BLE001
            print(f"=== {sym}: no lineage ({exc}) ===\n")
            continue
        print(f"=== {sym} ===")
        for field in (
            "records_received", "records_written", "duplicate_count",
            "plausibility_rejected", "plausibility_reasons",
            "partitions", "ingestion_time",
        ):
            print(f"  {field}: {data.get(field)}")
        print(f"  lineage: {json.dumps(data.get('lineage', {}), indent=4)}")
        print()


if __name__ == "__main__":
    main()
