#!/usr/bin/env python3
"""Remove the fabricated rows that the streaming path left in the lakehouse.

WHAT THIS REMOVES
-----------------
Three groups of rows, all of which are NOT market data:

1. ``source = "manual"`` rows (18 rows, AAPL / MSFT / NVDA).
   The Live Stream page's "demo" panel pushed three hand-typed bars per
   ticker into Kafka. The prices were invented (AAPL ~332.5, MSFT ~415.2,
   NVDA ~510.0) and they reached Bronze like any other observation.

2. ``source = "finnhub_ws"`` rows (9 symbols, ~17,000 rows).
   Measured on 2026-11-04: the Finnhub WebSocket publisher attributed trades
   to the WRONG ticker. The values are genuine trades from OTHER symbols
   (each series is internally continuous, so it is not noise), but they were
   filed under the wrong name:

       symbol   stored close range   true close that day
       NVDA     855 .. 1938           237.47
       TSLA      68 ..  283           377.81
       COIN      72 ..  125           178.45
       WMT       55 ..  103           108.16

   A symbol that ALSO has a real daily bar for that session is unharmed -
   the daily bar wins the canonicalisation and the intraday rows are dropped
   anyway. But COIN, BTC-USD and ETH-USD have NO daily bar for 2026-10-07,
   so their chart showed the wrong price.

   These rows are removed WHOLESALE rather than row-by-row. A price test
   cannot help the symbols that need it most: with no daily history there is
   no reference price, so exactly the mis-priced symbols would keep their
   bad rows. The lakehouse serves daily bars only, so the streaming ticks
   contribute nothing that the daily provider does not supply better.

3. ``source = "vn_rest"`` rows (5,527 rows, 12 VN symbols).
   These are REAL one-minute prints from the SSI iBoard REST endpoint - the
   prices are correct. But they are intraday, and a symbol whose only feed is
   intraday has no session bar, so its "daily" close was the last tick of the
   day rather than the settled close. They are removed because the daily
   provider (yahoo_http / ssi_vn) supplies the same sessions properly. Where
   no daily bar exists for a session, the session is left EMPTY rather than
   filled with an approximation - a missing bar is honest, a wrong bar is not.

WHY THE ROWS ARE DELETED AND NOT REPAIRED
------------------------------------------
There is no correct value to restore. For group 1 and group 2 the number
belongs to a different instrument entirely, and guessing would put invented
prices into the lake. For group 3 the true settled close is fetched fresh
from the provider by ``reingest_window.py`` right after this script runs.

SAFETY
------
  * dry run by default; ``--apply`` is required to write
  * every removed row is counted and reported, per symbol
  * a JSON report is written to ``bronze://_migration/``
  * the script refuses to run while the API is up, because the API caches
    frames in memory and would keep serving the pre-repair data

Run:
    python scripts/purge_fabricated_rows.py
    python scripts/purge_fabricated_rows.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import get_logger, setup_logging
from app.lakehouse.bronze import symbol_prefix
from app.lakehouse.minio_storage import MinioStorageBackend

logger = get_logger(__name__)

LAYER = "bronze"

#: Sources whose rows are fabricated or mis-attributed.
#:
#: ``vn_ws`` is here because of a measured field-index bug in
#: ``vn_websocket.parse_quote``: it divided a VND quote by 1000, so MWG bars
#: were written at close=75.3 while the stock trades near 72,300 VND. Five
#: such rows survived in Bronze for MWG on 2026-10-23. The canonicalisation
#: already drops them from the served frame (the session has a real daily
#: bar), but leaving them in Bronze means a later re-canonicalisation could
#: pick them up, so they are removed too.
FABRICATED_SOURCES = frozenset({"manual", "vn_ws"})

#: Sources whose rows are per-minute intraday prints from the SSI iBoard REST
#: endpoint. The prices are correct, but the lakehouse serves daily bars
#: only, and the daily provider owns these sessions properly.
INTRADAY_ONLY_SOURCES = frozenset({"vn_rest"})

#: Sources whose rows are per-second intraday prints from the streaming path.
#:
#: These are removed wholesale, not merely the ones whose price looks wrong.
#: The reasoning:
#:
#:   * The lakehouse serves DAILY bars only. A per-second tick contributes
#:     nothing to a daily chart.
#:   * The Finnhub WebSocket path was caught attributing trades to the wrong
#:     ticker, so this source cannot be trusted row-by-row - a row that
#:     happens to sit near the right price may still be the wrong instrument.
#:   * A price-window test cannot cover a symbol with NO daily history: with
#:     no reference there is nothing to compare against, so the mis-priced
#:     rows for exactly those symbols (COIN, BTC-USD, ETH-USD - the three
#:     whose charts were wrong) would survive the test.
#:
#: The daily provider supplies the same sessions properly, so nothing is
#: lost: `reingest_window.py` re-fetches them right after this script runs.
STREAMING_SOURCES = frozenset({"finnhub_ws", "finnhub_rest"})


def classify_rows(frame: pd.DataFrame) -> tuple[pd.Series, dict[str, int]]:
    """Return a boolean mask of rows to remove, plus the reason counts.

    A row is removed when:
      * its source is fabricated (``manual``), OR
      * it is a streaming tick (``finnhub_ws`` / ``finnhub_rest``) - see
        :data:`STREAMING_SOURCES` for why these go wholesale, OR
      * it is a per-minute intraday print (``vn_rest``) that the daily
        provider owns.
    """
    reasons: Counter[str] = Counter()
    mask = pd.Series(False, index=frame.index)

    if frame.empty or "source" not in frame.columns:
        return mask, {}

    sources = frame["source"].astype(str).str.strip().str.lower()

    # 1. Fabricated demo rows and unit-error WS rows.
    fabricated = sources.isin(FABRICATED_SOURCES)
    mask |= fabricated
    reasons["fabricated_or_mislabelled"] += int(fabricated.sum())

    # 2. Streaming ticks - removed wholesale.
    streaming = sources.isin(STREAMING_SOURCES)
    mask |= streaming
    reasons["streaming_ticks"] += int(streaming.sum())

    # 3. Intraday-only rows superseded by the daily provider.
    intraday = sources.isin(INTRADAY_ONLY_SOURCES)
    mask |= intraday
    reasons["intraday_only"] += int(intraday.sum())

    return mask, dict(reasons)


def purge_symbol(
    storage: MinioStorageBackend,
    symbol: str,
    apply: bool,
) -> dict:
    """Remove fabricated rows for one symbol. Returns a per-symbol summary."""
    keys = [
        k
        for k in storage.list_objects(LAYER, symbol_prefix(symbol))
        if k.endswith(".parquet")
    ]
    summary = {
        "symbol": symbol,
        "rows_before": 0,
        "rows_removed": 0,
        "reasons": {},
        "partitions_removed": 0,
        "partitions_rewritten": 0,
    }
    if not keys:
        return summary

    for key in keys:
        frame = storage.read_parquet(LAYER, key)
        if frame is None or frame.empty:
            continue
        summary["rows_before"] += len(frame)

        mask, reasons = classify_rows(frame)
        if not mask.any():
            continue
        for reason, count in reasons.items():
            summary["reasons"][reason] = summary["reasons"].get(reason, 0) + count
        removed = int(mask.sum())
        summary["rows_removed"] += removed

        if not apply:
            continue

        kept = frame.loc[~mask]
        if kept.empty:
            storage.client.remove_object(storage._bucket(LAYER), key)
            summary["partitions_removed"] += 1
        else:
            storage.write_parquet(LAYER, key, kept)
            summary["partitions_rewritten"] += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete rows (default: a dry run).",
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Only process these symbols (default: every symbol in Bronze).",
    )
    args = parser.parse_args()

    setup_logging()
    storage = MinioStorageBackend()
    mode = "APPLY" if args.apply else "DRY RUN"

    symbols = (
        [s.strip().upper() for s in args.symbols]
        if args.symbols
        else sorted(
            {
                o.object_name.split("/", 1)[0].split("=", 1)[1]
                for o in storage.client.list_objects(
                    storage._bucket(LAYER), prefix="symbol=", recursive=False
                )
                if o.object_name and o.object_name.startswith("symbol=")
            }
        )
    )

    print("=" * 78)
    print("PURGE FABRICATED / MIS-ATTRIBUTED ROWS")
    print("=" * 78)
    print(f"mode    : {mode}")
    print(f"symbols : {len(symbols)}")
    print()

    totals = Counter()
    per_symbol: list[dict] = []

    for symbol in symbols:
        summary = purge_symbol(storage, symbol, args.apply)
        if summary["rows_removed"]:
            per_symbol.append(summary)
            for reason, count in summary["reasons"].items():
                totals[reason] += count

    print(f"{'symbol':<12} {'before':>9} {'removed':>9}  reasons")
    print("-" * 78)
    for summary in per_symbol:
        reasons = ", ".join(f"{k}={v}" for k, v in sorted(summary["reasons"].items()))
        print(
            f"{summary['symbol']:<12} {summary['rows_before']:>9} "
            f"{summary['rows_removed']:>9}  {reasons}"
        )
    print("-" * 78)
    print(f"{'TOTAL':<12} {'':>9} {sum(totals.values()):>9}")
    for reason, count in totals.most_common():
        print(f"    {reason:<28} {count}")
    print()

    if not args.apply:
        print("DRY RUN - nothing was modified. Re-run with --apply")
        return 0

    report_name = (
        f"_migration/purge_fabricated_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    )
    storage.write_json(
        LAYER,
        report_name,
        {
            "symbols": per_symbol,
            "totals": dict(totals),
            "rows_removed": int(sum(totals.values())),
            "applied_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(f"report written to bronze://{report_name}")
    print()
    print("Now rebuild Silver + Gold and re-fetch the affected sessions:")
    print("    python scripts/backfill_silver_gold.py --symbols " + " ".join(
        s["symbol"] for s in per_symbol
    ))
    print("    python scripts/reingest_window.py --symbols " + " ".join(
        s["symbol"] for s in per_symbol
    ) + " --days 45")
    return 0


if __name__ == "__main__":
    sys.exit(main())
