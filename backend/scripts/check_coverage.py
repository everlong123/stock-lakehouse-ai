"""Report lakehouse coverage: which symbols have Bronze/Silver/Gold data.

Run from the backend directory:

    .venv/Scripts/python.exe scripts/check_coverage.py

The GLOBAL_SYMBOLS universe is ~958 tickers, but "we ran a backfill" does not
mean every one of them landed in every layer: a provider can fail for a single
ticker, a symbol can be delisted, and the symbol lists used by the three
layers drift independently as new runs append. This prints, per layer, how many
of the expected symbols are present and which ones are not, so the gap can be
backfilled selectively instead of re-running the whole pass.

Bronze/Silver/Gold objects are laid out as::

    symbol=<SYM>/year=YYYY/month=MM/part-NNN.parquet

Silver and Bronze also keep an `_errors/` prefix for symbols whose transform
failed. Those objects are filtered out, so a symbol that only ever produced
errors is reported as missing rather than as covered.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.constants import GLOBAL_SYMBOLS
from app.core.logging_config import get_logger
from app.lakehouse.minio_storage import MinioStorageBackend

logger = get_logger(__name__)

LAYERS = ("bronze", "silver", "gold")


def symbols_in_layer(storage: MinioStorageBackend, layer: str) -> set[str]:
    """Distinct symbols that have at least one real (non-error) object."""
    found: set[str] = set()
    for key in storage.list_objects(layer):
        if key.startswith("_errors/") or "/_errors/" in key:
            continue
        if not key.startswith("symbol="):
            continue
        symbol = key.split("/", 1)[0].split("=", 1)[1].strip().upper()
        if symbol:
            found.add(symbol)
    return found


def report_missing(label: str, missing: set[str], limit: int = 15) -> None:
    if not missing:
        return
    shown = sorted(missing)[:limit]
    logger.info("  %s (%d): %s", label, len(missing), ", ".join(shown))
    if len(missing) > limit:
        logger.info("  %s ... and %d more", label, len(missing) - limit)


def main() -> int:
    storage = MinioStorageBackend()
    expected = {s.upper() for s in GLOBAL_SYMBOLS}
    logger.info("expected symbols: %d", len(expected))

    per_layer: dict[str, set[str]] = {}
    for layer in LAYERS:
        try:
            found = symbols_in_layer(storage, layer)
        except Exception as exc:  # noqa: BLE001 - keep scanning other layers
            logger.error("%s: scan failed: %s", layer, exc)
            per_layer[layer] = set()
            continue

        per_layer[layer] = found
        logger.info(
            "%-7s present=%4d  missing=%4d  extra=%d",
            layer, len(found), len(expected - found), len(found - expected),
        )
        report_missing("missing", expected - found)

    complete = set(expected)
    for layer in LAYERS:
        complete &= per_layer.get(layer, set())

    logger.info("=" * 60)
    logger.info("complete (all three layers): %d / %d", len(complete), len(expected))

    # Group the incomplete symbols by which layers they do have, so the shapes
    # of the gaps are visible: "bronze only" means the transform never ran,
    # "bronze+silver" means Gold is missing, etc.
    buckets: dict[str, set[str]] = defaultdict(set)
    for symbol in expected - complete:
        present = [layer for layer in LAYERS if symbol in per_layer.get(layer, set())]
        buckets["+".join(present) or "none"].add(symbol)

    if buckets:
        logger.info("incomplete symbols by what they do have:")
        for combo in sorted(buckets, key=lambda key: -len(buckets[key])):
            symbols = sorted(buckets[combo])
            logger.info("  [%s] %d", combo, len(symbols))
            report_missing(combo, set(symbols), limit=20)

    unexpected = set()
    for layer in LAYERS:
        unexpected |= per_layer.get(layer, set()) - expected
    if unexpected:
        logger.info("objects exist for %d symbols outside GLOBAL_SYMBOLS", len(unexpected))
        report_missing("unexpected", unexpected, limit=20)

    return 0 if len(complete) == len(expected) else 1


if __name__ == "__main__":
    raise SystemExit(main())