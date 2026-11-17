"""Fast parallel scan of Bronze vs Silver vs Gold divergence.

WHY A SEPARATE SCRIPT
---------------------
`check_layer_divergence.py` reads all three layers for every symbol
SEQUENTIALLY. Measured on 2026-11-12: 20 symbols took 52s, so the full
1002-symbol universe needs ~44 minutes - too slow to run during a
diagnostic.

This script does the same comparison but:
  * reads only the NEWEST monthly partition of each layer (the divergence
    that matters is in the recent bars, and the full history is compared by
    the slow script), and
  * runs the symbols on a thread pool (the work is MinIO I/O bound).

Usage:
    .venv/Scripts/python.exe scripts/scan_divergence_fast.py [--days 30] [--workers 16]
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import get_logger, setup_logging  # noqa: E402
from app.lakehouse.bronze import BronzeLayer  # noqa: E402
from app.lakehouse.gold import GoldLayer  # noqa: E402
from app.lakehouse.silver import SilverLayer  # noqa: E402

logger = get_logger(__name__)

TOLERANCE = 1e-6


def newest_partition(layer, symbol: str) -> pd.DataFrame:
    """Read the newest monthly partition of one layer for one symbol."""
    keys = [
        k for k in layer.storage.list_objects(layer.layer_name, f"symbol={symbol}/")
        if k.endswith(".parquet")
    ]
    if not keys:
        return pd.DataFrame()
    newest = sorted(keys)[-1]
    try:
        return layer.storage.read_parquet(layer.layer_name, newest)
    except Exception as exc:  # noqa: BLE001
        logger.warning("read failed for %s %s: %s", layer.layer_name, symbol, exc)
        return pd.DataFrame()


def _session_index(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per trading day, keyed by the day."""
    if frame.empty or "timestamp" not in frame.columns:
        return pd.DataFrame()
    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
    working = working.dropna(subset=["timestamp"])
    if working.empty:
        return pd.DataFrame()
    working["_day"] = working["timestamp"].dt.strftime("%Y-%m-%d")
    return working


def compare(stored: pd.DataFrame, source: pd.DataFrame, days: int) -> list[dict]:
    """Sessions where the stored close disagrees with the source close."""
    a = _session_index(stored)
    b = _session_index(source)
    if a.empty or b.empty:
        return []
    if days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        a = a[a["_day"] >= cutoff]
        b = b[b["_day"] >= cutoff]
        if a.empty or b.empty:
            return []
    a = a.drop_duplicates(subset=["_day"], keep="last")
    b = b.drop_duplicates(subset=["_day"], keep="last")
    merged = a[["_day", "close"]].merge(
        b[["_day", "close"]], on="_day", how="inner", suffixes=("_stored", "_source")
    )
    if merged.empty:
        return []
    stored_close = pd.to_numeric(merged["close_stored"], errors="coerce")
    source_close = pd.to_numeric(merged["close_source"], errors="coerce")
    diff = (stored_close - source_close).abs()
    scale = source_close.abs().clip(lower=1e-9)
    differing = merged[(diff / scale) > TOLERANCE]
    findings: list[dict] = []
    for _, row in differing.iterrows():
        findings.append(
            {
                "day": row["_day"],
                "stored": float(row["close_stored"]),
                "source": float(row["close_source"]),
                "rel": float(diff.loc[row.name] / scale.loc[row.name]),
            }
        )
    return findings


def scan_one(symbol: str, bronze, silver, gold, days: int) -> dict | None:
    b = newest_partition(bronze, symbol)
    s = newest_partition(silver, symbol)
    g = newest_partition(gold, symbol)
    silver_diff = compare(s, b, days)
    gold_diff = compare(g, b, days)
    if not silver_diff and not gold_diff:
        return None
    return {"symbol": symbol, "silver": silver_diff, "gold": gold_diff}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args(argv)

    setup_logging()

    bronze = BronzeLayer()
    silver = SilverLayer()
    gold = GoldLayer()

    symbols: set[str] = set()
    for key in bronze.storage.list_objects("bronze", ""):
        if key.startswith("symbol="):
            symbols.add(key.split("/", 1)[0].split("=", 1)[1])
    symbols = sorted(symbols)
    if args.limit:
        symbols = symbols[: args.limit]

    print(f"Scanning {len(symbols)} symbol(s), trailing {args.days} days, "
          f"{args.workers} workers")
    print()

    divergent: list[dict] = []
    errors = 0
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(scan_one, sym, bronze, silver, gold, args.days): sym
            for sym in symbols
        }
        for future in as_completed(futures):
            sym = futures[future]
            done += 1
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("scan failed for %s: %s", sym, exc)
                errors += 1
                continue
            if result:
                divergent.append(result)
            if done % 100 == 0:
                print(f"  {done}/{len(symbols)} checked, {len(divergent)} divergent")

    divergent.sort(key=lambda item: item["symbol"])
    print()
    print("=" * 78)
    print(f"symbols checked        : {len(symbols)}")
    print(f"symbols with divergence: {len(divergent)}")
    print(f"errors                 : {errors}")
    print("=" * 78)

    if divergent:
        print()
        by_day: dict[str, int] = {}
        for entry in divergent:
            for item in entry["silver"] + entry["gold"]:
                by_day[item["day"]] = by_day.get(item["day"], 0) + 1
        print("divergent sessions by day:")
        for day, count in sorted(by_day.items()):
            print(f"  {day}  {count} symbol(s)")
        print()
        print("DIVERGENT SYMBOLS:")
        for entry in divergent:
            sessions = sorted({d["day"] for d in entry["silver"] + entry["gold"]})
            print(f"  {entry['symbol']:<12} {len(sessions)} session(s): "
                  f"{', '.join(sessions[-6:])}")
        print()
        print("Fix with a forced rebuild (the watermark check cannot see this):")
        print("    python scripts/backfill_silver_gold.py --symbols <SYM> --force")

    if args.out:
        Path(args.out).write_text(
            json.dumps(divergent, indent=1, default=str), encoding="utf-8"
        )
        print(f"\nWrote {args.out}")
    return 1 if divergent else 0


if __name__ == "__main__":
    raise SystemExit(main())
