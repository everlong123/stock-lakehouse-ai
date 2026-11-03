"""Count the objects in each lakehouse layer and print them as JSON.

WHY THIS IS A SEPARATE SCRIPT
-----------------------------
Counting the layers walks ~340k object keys in MinIO. The MinIO client
yields them one at a time, and every step of that iteration runs Python
code in the FastAPI process, so the job holds the GIL for as long as it
runs (~19s, and much longer when the auto-refresh pass is hammering the
same MinIO instance).

A GIL-holding job in the API process starves EVERY other endpoint: the
dashboard, the market history, the agent - they all queue behind it. That
is what made a plain browser reload take a minute.

Running the count in its own process removes the contention entirely: the
API process never touches those 340k keys, so it stays responsive while
the count runs. The script prints one JSON object on stdout and nothing
else, so the caller can parse it directly.

Usage:
    python scripts/count_layer_objects.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python scripts/count_layer_objects.py` from the backend root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.bronze import BronzeLayer  # noqa: E402
from app.lakehouse.gold import GoldLayer  # noqa: E402
from app.lakehouse.silver import SilverLayer  # noqa: E402


def main() -> int:
    layers = (
        ("bronze", BronzeLayer),
        ("silver", SilverLayer),
        ("gold", GoldLayer),
    )
    counts: dict[str, int] = {}
    for name, cls in layers:
        try:
            counts[name] = int(cls().record_count())
        except Exception as exc:  # noqa: BLE001 - report the failure, keep going
            print(f"record_count failed for {name}: {exc}", file=sys.stderr)
            counts[name] = -1
    # The caller parses the LAST line of stdout, so anything the application
    # logged to stdout earlier cannot break it.
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
