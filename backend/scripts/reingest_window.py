#!/usr/bin/env python3
"""Re-ingest a window of history so provider restatements are picked up.

WHY THIS EXISTS
---------------
``verify_against_source.py`` reports bars where the provider has revised a
session it had already published. The lakehouse keeps the OLD value, because
the incremental refresh only re-fetches the last few days:

    start = latest_stored_timestamp - AUTO_REFRESH_OVERLAP_DAYS   # 5 days

A restatement older than that window is never re-fetched, so it stays wrong
in Bronze, Silver and Gold - and therefore on the web - forever.

Measured on 2026-11-03, 15 symbols had restated bars, e.g.:

    005930.KS  2026-10-23  stored close 212250 / high 214500 / vol 11326064
                          Yahoo now   close 215500 / high 215500 / vol 16145972
    AAL        2026-10-21  stored open 12.19 / close 12.235 / vol 76690128
                          Yahoo now   open 12.2  / close 12.24  / vol 76927200

The fix is a targeted re-ingest: fetch the affected window from the
provider, append it to Bronze (whose dedupe keeps the newer row for the
same ``(symbol, timestamp)``), then rebuild Silver and Gold for that symbol.

WHY A SEPARATE SCRIPT AND NOT JUST A REFRESH
--------------------------------------------
The refresh pass is incremental by design and skips symbols whose newest bar
is fresh, so it will never revisit a 2-week-old session. This script is the
explicit "go and get that window again" operation.

USAGE
-----
    # preview only
    python scripts/reingest_window.py --symbols AAL 005930.KS --days 30 --dry-run

    # actually re-ingest, then rebuild Silver + Gold
    python scripts/reingest_window.py --symbols AAL 005930.KS --days 30

    # take the symbol list straight from a verification run
    python scripts/verify_against_source.py --symbols all > verify.txt
    python scripts/reingest_window.py --symbols-from verify.txt --days 45

EXIT CODES
----------
    0 = every requested symbol was re-ingested (or was already correct)
    1 = at least one symbol failed
    2 = the run could not start
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import get_logger, setup_logging
from app.data_sources.factory import get_data_provider
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.gold import GoldLayer
from app.lakehouse.silver import SilverLayer

logger = get_logger(__name__)


def _session_key(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce").dt.date


def fetch_window(symbol: str, provider, days: int) -> pd.DataFrame:
    """Fetch the trailing ``days`` of daily bars straight from the provider."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    frame = provider.get_historical_data(symbol, start=start, end=end, interval="1d")
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    for col in ("open", "high", "low", "close", "adj_close", "volume"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def diff_window(
    symbol: str,
    stored: pd.DataFrame,
    fetched: pd.DataFrame,
    tolerance: float,
) -> list[dict]:
    """List the sessions where the fetched value differs from the stored one."""
    if stored.empty or fetched.empty:
        return []

    stored = stored.copy()
    stored["_session"] = _session_key(stored["timestamp"])
    fetched = fetched.copy()
    fetched["_session"] = _session_key(fetched["timestamp"])

    merged = fetched.merge(
        stored[["_session", "close", "volume"]],
        on="_session",
        how="inner",
        suffixes=("_new", "_old"),
    )
    if merged.empty:
        return []

    price_diff = (merged["close_new"] - merged["close_old"]).abs()
    volume_diff = (merged["volume_new"].fillna(0) - merged["volume_old"].fillna(0)).abs()
    rel = price_diff / merged["close_old"].abs().clip(lower=1e-9)

    changed = merged[(rel > tolerance) | (volume_diff > 0)]

    findings: list[dict] = []
    for _, row in changed.iterrows():
        price_rel = float(rel.loc[row.name])
        price_changed = price_rel > tolerance
        vol_old = row["volume_old"]
        vol_new = row["volume_new"]
        vol_changed = (
            pd.notna(vol_old)
            and pd.notna(vol_new)
            and abs(float(vol_new) - float(vol_old)) > 0
        )
        findings.append(
            {
                "session": str(row["_session"]),
                "close_old": float(row["close_old"]),
                "close_new": float(row["close_new"]),
                "volume_old": float(vol_old) if pd.notna(vol_old) else None,
                "volume_new": float(vol_new) if pd.notna(vol_new) else None,
                "rel": price_rel,
                "price_changed": price_changed,
                "volume_changed": bool(vol_changed),
            }
        )
    return findings


def reingest_symbol(
    symbol: str,
    provider,
    days: int,
    tolerance: float,
    dry_run: bool,
    api_url: str | None = None,
) -> dict:
    """Re-fetch, diff and (unless dry-run) write one symbol's window."""
    result = {"symbol": symbol, "changed": [], "written": False, "error": ""}

    try:
        fetched = fetch_window(symbol, provider, days)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"fetch failed: {exc}"
        return result
    if fetched.empty:
        result["error"] = "provider returned no rows"
        return result

    bronze = BronzeLayer()
    try:
        stored = bronze.read(symbol)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"bronze read failed: {exc}"
        return result

    # Diff against EVERY layer, not just Bronze.
    #
    # WHY: Bronze is the layer the write path fixes first, so a symbol whose
    # Bronze is already correct can still have a stale Silver and Gold - the
    # layers are rebuilt separately, and a killed refresh can leave them
    # behind. Measured on 2026-11-05: ADS.DE held the revised 168.10 in
    # Bronze but the pre-revision 168.85 in Silver and Gold, because the
    # script compared only against Bronze, concluded "no differences", and
    # skipped the rebuild entirely. The web then served 168.85 forever.
    #
    # So the layers are compared independently and the symbol is rebuilt when
    # ANY of them disagrees with the provider.
    layer_frames: dict[str, pd.DataFrame] = {"bronze": stored}
    for layer_name, layer_cls in (("silver", SilverLayer), ("gold", GoldLayer)):
        try:
            layer_frames[layer_name] = layer_cls().read(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read %s for %s: %s", layer_name, symbol, exc)
            layer_frames[layer_name] = pd.DataFrame()

    differing_layers: list[str] = []
    for layer_name, layer_frame in layer_frames.items():
        changes = diff_window(symbol, layer_frame, fetched, tolerance)
        if changes:
            differing_layers.append(layer_name)
            result.setdefault("layer_changes", {})[layer_name] = changes

    # Bronze is the source of truth for the rebuild, so its diff drives the
    # write; the other layers only decide WHETHER a rebuild is needed.
    result["changed"] = result.get("layer_changes", {}).get("bronze", [])
    result["differing_layers"] = differing_layers
    if not differing_layers:
        return result
    if dry_run:
        return result

    # Append to Bronze. Its dedupe drops rows with the same
    # (symbol, timestamp) keeping the LAST one, so the freshly fetched
    # value wins over the stale one.
    #
    # The append is only needed when BRONZE itself disagrees. When Bronze is
    # already correct and only Silver/Gold lag behind, writing Bronze again
    # is a no-op that still costs a full partition read+write, and - because
    # the rows are identical - it would not even change anything.
    if "bronze" in differing_layers:
        try:
            meta = bronze.append(fetched, lineage={
                "source": "reingest_window",
                "provider": getattr(provider, "source_name", "unknown"),
                "symbol": symbol,
                "interval": "1d",
                "start": str(fetched["timestamp"].min()),
                "end": str(fetched["timestamp"].max()),
            })
            result["written"] = True
            result["records_written"] = meta.get("records_written")
            result["new_records"] = meta.get("new_records")
            result["updated_records"] = meta.get("updated_records")
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"bronze append failed: {exc}"
            return result
    else:
        result["written"] = False
        result["bronze_already_current"] = True

    # Rebuild Silver and Gold from the corrected Bronze.
    #
    # NOTE: `transform_to_silver(symbol)` re-reads Bronze from storage rather
    # than taking a frame, which is what we want - the point of the rebuild
    # is to pick up the corrected rows that were just written.
    try:
        from app.pipelines.orchestrator import build_gold_layer, transform_to_silver

        transform_to_silver(symbol, interval="1d")
        gold_info = build_gold_layer(symbol)
        result["rebuilt"] = True
        result["gold_records"] = gold_info.get("records")
    except Exception as exc:  # noqa: BLE001
        # The Bronze write already happened, so the correction IS stored. The
        # Silver/Gold rebuild can be redone separately with
        # `backfill_silver_gold.py --symbols <SYM>`.
        result["error"] = f"silver/gold rebuild failed (bronze is corrected): {exc}"

    # Drop the API's memoised frame for this symbol.
    #
    # WHY: `MarketService` caches each symbol's frame for 15 minutes. Without
    # this the API keeps serving the OLD prices even though Bronze/Silver/Gold
    # now hold the corrected ones - so a verification run right after a
    # re-ingest would report a mismatch that no longer exists in storage.
    #
    # The script runs in its own process, so it cannot clear the API's cache
    # in-process; it asks the API over HTTP instead.
    if api_url:
        try:
            import json as _json
            import urllib.request as _urllib

            url = f"{api_url.rstrip('/')}/admin/auto-refresh/cache/invalidate?symbols={symbol}"
            # The endpoint is POST-only. A GET returns "405 Method Not Allowed",
            # so the cache was NEVER invalidated and the API kept serving the
            # pre-correction frame - which then showed up as a RESTATED
            # mismatch in the verification run that followed the re-ingest.
            request = _urllib.Request(url, method="POST")
            with _urllib.urlopen(request, timeout=15) as response:
                _json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache invalidation via API failed for %s: %s", symbol, exc)

    return result


def read_symbols_from_file(path: str) -> list[str]:
    """Pull symbol tokens out of a verification report."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    symbols: list[str] = []
    for line in text.splitlines():
        # The report prints "affected symbols: A, B, C" at the end.
        if "affected symbols:" in line:
            tail = line.split("affected symbols:", 1)[1]
            for token in tail.replace("\n", " ").split(","):
                token = token.strip()
                if token and token.replace(".", "").replace("-", "").isalnum():
                    symbols.append(token.upper())
    return symbols


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Symbols to re-ingest")
    parser.add_argument("--symbols-from", default=None,
                        help="Read the symbol list from a verify_against_source.py report")
    parser.add_argument("--days", type=int, default=45,
                        help="How many trailing days to re-fetch (default 45)")
    parser.add_argument("--provider", default="yahoo_http")
    parser.add_argument("--tolerance", type=float, default=1e-6,
                        help="Relative price difference treated as unchanged")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change, write nothing")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api/v1",
                        help="Base URL of the running API, used to drop its cached "
                             "copy of the corrected symbol so the change is visible "
                             "immediately. Pass '' to skip.")
    args = parser.parse_args(argv)

    setup_logging()
    from app.data_sources.factory import get_data_provider

    symbols: list[str] = list(args.symbols or [])
    if args.symbols_from:
        symbols.extend(read_symbols_from_file(args.symbols_from))
    symbols = sorted({s.upper() for s in symbols if s})

    if not symbols:
        print("No symbols given. Use --symbols or --symbols-from.")
        return 2

    api_url = args.api_url or None

    print("=" * 78)
    print("RE-INGESTING PROVIDER RESTATEMENTS")
    print("=" * 78)
    print(f"symbols : {len(symbols)}")
    print(f"window  : trailing {args.days} days")
    print(f"mode    : {'DRY RUN (no writes)' if args.dry_run else 'WRITE'}")
    if api_url:
        print(f"api     : {api_url}")
    print()

    try:
        provider = get_data_provider(args.provider)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot build provider '{args.provider}': {exc}")
        return 2

    failures = 0
    changed_count = 0
    for symbol in symbols:
        result = reingest_symbol(symbol, provider, args.days, args.tolerance,
                                 args.dry_run, api_url=api_url)
        if result["error"] and not result["changed"] and not result.get("differing_layers"):
            print(f"[ERROR] {symbol:<10} {result['error']}")
            failures += 1
            continue
        differing = result.get("differing_layers") or []
        if not differing:
            print(f"[ OK  ] {symbol:<10} no differences")
            continue
        changed_count += 1
        # A symbol can differ in Silver/Gold while Bronze is already correct.
        # In that case nothing is WRITTEN to Bronze, but the rebuild still
        # happens - that is the whole point of the layer-aware diff.
        tag = "DRY" if args.dry_run else (
            "WROTE" if result["written"] else ("REBLD" if result.get("rebuilt") else "FAIL")
        )
        layer_tag = ",".join(differing)
        print(f"[{tag:>5}] {symbol:<10} {layer_tag}: differs")
        for change in result["changed"][:8]:
            if change["price_changed"]:
                print(
                    f"          {change['session']}  close {change['close_old']:.4f} -> "
                    f"{change['close_new']:.4f}  (rel {change['rel']:.4%})"
                )
            else:
                print(
                    f"          {change['session']}  close unchanged "
                    f"({change['close_old']:.4f}), volume "
                    f"{change['volume_old']} -> {change['volume_new']}"
                )
        if len(result["changed"]) > 8:
            print(f"          ... and {len(result['changed']) - 8} more")
        for layer_name, changes in (result.get("layer_changes") or {}).items():
            if layer_name == "bronze":
                continue
            print(f"          {layer_name}: {len(changes)} session(s) differ")
        if result["error"]:
            print(f"          note: {result['error']}")
            failures += 1

    print()
    print("=" * 78)
    print(f"symbols with differences : {changed_count}")
    print(f"failures                 : {failures}")
    print("=" * 78)
    if args.dry_run:
        print("Dry run - nothing was written.")
    else:
        print("Re-ingest complete. Verify with:")
        print("    python scripts/verify_against_source.py --symbols ...")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
