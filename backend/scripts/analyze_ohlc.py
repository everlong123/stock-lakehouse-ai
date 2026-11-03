"""Quantify OHLC violations across the lakehouse, to decide how to repair them.

Run from the backend directory:

    .venv/Scripts/python.exe scripts/analyze_ohlc.py [objects_per_layer]

Reads a sample of Bronze/Silver/Gold objects and reports, per layer:

  * how many rows violate each OHLC invariant
  * the magnitude of each violation, relative to the close
  * whether violations cluster on the most recent bar (Yahoo returns a
    still-forming bar, whose open/high/low are not yet internally consistent)
  * whether any row has high < low, which would mean the row is unusable
    rather than merely repairable

The magnitude numbers decide the repair strategy: a violation of a fraction of
a percent is a rounding / stale-open artefact and can be clamped safely, while
a violation of tens of percent means the row itself is garbage and should be
dropped rather than "fixed".
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from app.core.logging_config import get_logger
from app.lakehouse.minio_storage import MinioStorageBackend

logger = get_logger(__name__)

LAYERS = ("bronze", "silver", "gold")
SAMPLE_PER_LAYER = 300


def analyse(storage: MinioStorageBackend, layer: str, sample_size: int) -> pd.DataFrame:
    keys = [k for k in storage.list_objects(layer) if k.endswith(".parquet") and "_errors" not in k]
    if not keys:
        return pd.DataFrame()

    picked = keys if len(keys) <= sample_size else random.sample(keys, sample_size)
    frames = []
    for key in picked:
        try:
            frame = storage.read_parquet(layer, key)
        except Exception as exc:  # noqa: BLE001 - a bad object must not stop the scan
            logger.warning("  unreadable %s: %s", key, exc)
            continue
        if not {"open", "high", "low", "close"}.issubset(frame.columns):
            continue
        frames.append(frame)

    if not frames:
        return pd.DataFrame()
    data = pd.concat(frames, ignore_index=True)
    data["layer"] = layer
    return data


def violations(frame: pd.DataFrame) -> pd.DataFrame:
    """Return one row per violation, with the offending magnitude."""
    close = frame["close"].abs().clip(lower=1e-9)
    rows = []
    for name, bad in {
        "high<open": frame["high"] < frame["open"],
        "high<close": frame["high"] < frame["close"],
        "low>open": frame["low"] > frame["open"],
        "low>close": frame["low"] > frame["close"],
        "high<low": frame["high"] < frame["low"],
        "negative_price": (frame[["open", "high", "low", "close"]] < 0).any(axis=1),
        "zero_close": frame["close"] <= 0,
    }.items():
        if not bad.any():
            continue
        subset = frame[bad]
        magnitude = {
            "high<open": (subset["open"] - subset["high"]) / close[bad],
            "high<close": (subset["close"] - subset["high"]) / close[bad],
            "low>open": (subset["low"] - subset["open"]) / close[bad],
            "low>close": (subset["low"] - subset["close"]) / close[bad],
            "high<low": (subset["low"] - subset["high"]) / close[bad],
            "negative_price": (subset[["open", "high", "low", "close"]].min(axis=1).abs()) / close[bad],
            "zero_close": 1.0,
        }[name]
        rows.append(
            pd.DataFrame(
                {
                    "kind": name,
                    "n": len(subset),
                    "pct_of_rows": 100.0 * len(subset) / len(frame),
                    "mag_max_pct": 100.0 * float(magnitude.max()),
                    "mag_median_pct": 100.0 * float(magnitude.median()),
                }
            )
        )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> int:
    sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE_PER_LAYER
    storage = MinioStorageBackend()

    for layer in LAYERS:
        frame = analyse(storage, layer, sample_size)
        if frame.empty:
            logger.info("%s: no sample rows", layer)
            continue

        logger.info("=" * 64)
        logger.info("%s: sampled %d objects -> %d rows", layer, sample_size, len(frame))

        table = violations(frame)
        if table.empty:
            logger.info("  no OHLC violations in the sample")
            continue

        for _, row in table.sort_values("pct_of_rows", ascending=False).iterrows():
            logger.info(
                "  %-15s n=%5d  %6.3f%% of rows  magnitude: median %.4f%%  max %.2f%%",
                row["kind"], row["n"], row["pct_of_rows"],
                row["mag_median_pct"], row["mag_max_pct"],
            )

        # Are violations concentrated on the newest bar of each symbol?
        bad_mask = (
            (frame["high"] < frame[["open", "close"]].max(axis=1))
            | (frame["low"] > frame[["open", "close"]].min(axis=1))
        )
        if bad_mask.any():
            newest = frame.groupby("symbol")["timestamp"].transform("max")
            on_newest = bad_mask & (frame["timestamp"] == newest)
            logger.info(
                "  violations on each symbol's newest bar: %d of %d bad rows (%.0f%%)",
                int(on_newest.sum()), int(bad_mask.sum()),
                100.0 * on_newest.sum() / max(1, bad_mask.sum()),
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())