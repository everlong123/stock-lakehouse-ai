"""Golden test: the vectorised canonicalisation must match the original loop.

The original implementation is preserved verbatim below as the reference.
"""
import sys, time
sys.path.insert(0, ".")
import pandas as pd

from app.lakehouse.session import (
    _is_already_one_row_per_day,
    _is_daily_bar_source,
    _modal_stamp,
    _aggregate_intraday,
    canonicalize_daily_sessions,
    PRICE_COLUMNS,
)


def reference_canonicalize(frame):
    """The ORIGINAL implementation, verbatim."""
    report = {
        "rows_in": int(len(frame)),
        "rows_out": 0,
        "days_in": 0,
        "days_out": 0,
        "duplicate_session_rows_dropped": 0,
        "intraday_days_aggregated": 0,
        "intraday_rows_aggregated": 0,
    }
    if frame.empty:
        return frame.copy(), report

    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True, errors="coerce")
    working = working[working["timestamp"].notna()].copy()
    if working.empty:
        return frame.iloc[0:0].copy(), report

    working["_day"] = working["timestamp"].dt.date
    working["_stamp"] = working["timestamp"].dt.strftime("%H:%M")
    working["_is_daily_bar"] = working["source"].map(_is_daily_bar_source) if "source" in working.columns else True

    symbol_stamp = _modal_stamp(working["_stamp"])
    working["_symbol_stamp"] = symbol_stamp

    if "symbol" in working.columns:
        group_keys = ["symbol", "_day"]
    else:
        group_keys = ["_day"]

    if _is_already_one_row_per_day(working, group_keys):
        out = working.drop(columns=["_day", "_stamp", "_is_daily_bar", "_symbol_stamp"])
        original_columns = [c for c in frame.columns if c in out.columns]
        out = out.loc[:, original_columns + [c for c in out.columns if c not in original_columns]]
        out = out.sort_values("timestamp").reset_index(drop=True)
        report["rows_in"] = int(len(frame))
        report["rows_out"] = int(len(out))
        report["days_in"] = int(len(out))
        report["days_out"] = int(out["timestamp"].dt.date.nunique())
        return out, report

    kept_rows = []
    aggregated_rows = []

    for _group_key, day_frame in working.groupby(group_keys, sort=True):
        report["days_in"] += 1
        daily = day_frame[day_frame["_is_daily_bar"]]
        intraday = day_frame[~day_frame["_is_daily_bar"]]

        if not daily.empty:
            daily = daily.copy()
            daily["_matches"] = daily["_stamp"] == symbol_stamp
            if "ingestion_time" in daily.columns:
                daily["_ingest"] = pd.to_datetime(daily["ingestion_time"], utc=True, errors="coerce")
            else:
                daily["_ingest"] = pd.Timestamp("1970-01-01", tz="UTC")
            daily = daily.sort_values(["_matches", "_ingest"], ascending=[False, False], kind="mergesort")
            survivor = daily.iloc[0]
            kept_rows.append(survivor)
            dropped = len(day_frame) - 1
            report["duplicate_session_rows_dropped"] += dropped
            continue

        if intraday.empty:
            continue
        usable = intraday.dropna(subset=list(PRICE_COLUMNS))
        if usable.empty:
            report["duplicate_session_rows_dropped"] += len(day_frame)
            continue
        report["intraday_days_aggregated"] += 1
        report["intraday_rows_aggregated"] += len(day_frame)

        bar = _aggregate_intraday(usable)
        row = usable.iloc[0].copy()
        for column in PRICE_COLUMNS:
            row[column] = bar[column]
        if "volume" in row.index:
            row["volume"] = bar["volume"]
        if "adj_close" in row.index:
            row["adj_close"] = bar["adj_close"]
        if symbol_stamp:
            hour, _, minute = symbol_stamp.partition(":")
            day_value = pd.Timestamp(day_frame["_day"].iloc[0])
            try:
                row["timestamp"] = pd.Timestamp(
                    year=day_value.year, month=day_value.month, day=day_value.day,
                    hour=int(hour), minute=int(minute), tz="UTC",
                )
            except (ValueError, TypeError):
                pass
        aggregated_rows.append(row)

    survivors = kept_rows + aggregated_rows
    if not survivors:
        report["rows_out"] = 0
        report["days_out"] = 0
        return frame.iloc[0:0].copy(), report

    out = pd.DataFrame(survivors).reset_index(drop=True)
    out = out.drop(columns=[c for c in ("_day", "_stamp", "_is_daily_bar", "_symbol_stamp", "_matches", "_ingest") if c in out.columns])
    out = out.sort_values("timestamp").reset_index(drop=True)
    original_columns = [c for c in frame.columns if c in out.columns]
    out = out.loc[:, original_columns + [c for c in out.columns if c not in original_columns]]
    report["rows_out"] = int(len(out))
    report["days_out"] = int(out["timestamp"].dt.date.nunique())
    return out, report


def compare(name, frame):
    t0 = time.time()
    ref_out, ref_rep = reference_canonicalize(frame)
    t_ref = time.time() - t0

    t0 = time.time()
    new_out, new_rep = canonicalize_daily_sessions(frame)
    t_new = time.time() - t0

    ok = True
    if list(ref_out.columns) != list(new_out.columns):
        print(f"  [{name}] COLUMN MISMATCH\n    ref={list(ref_out.columns)}\n    new={list(new_out.columns)}")
        ok = False
    elif not ref_out.reset_index(drop=True).equals(new_out.reset_index(drop=True)):
        print(f"  [{name}] ROW MISMATCH ref={len(ref_out)} new={len(new_out)}")
        for c in ref_out.columns:
            if not ref_out[c].reset_index(drop=True).equals(new_out[c].reset_index(drop=True)):
                print(f"     column differs: {c}")
        ok = False

    keys = ["rows_in", "rows_out", "days_in", "days_out",
            "duplicate_session_rows_dropped", "intraday_days_aggregated",
            "intraday_rows_aggregated"]
    for k in keys:
        if ref_rep[k] != new_rep[k]:
            print(f"  [{name}] REPORT MISMATCH {k}: ref={ref_rep[k]} new={new_rep[k]}")
            ok = False

    status = "OK  " if ok else "FAIL"
    print(f"  [{name}] {status} rows={len(frame)} ref={t_ref:.2f}s new={t_new:.2f}s speedup={t_ref/max(t_new,1e-6):.1f}x")
    return ok


if __name__ == "__main__":
    from app.lakehouse.bronze import BronzeLayer

    all_ok = True
    for sym in ("AAPL", "ADS.DE", "VNM", "VCB", "MSFT"):
        try:
            bf = BronzeLayer().read(sym)
        except Exception as exc:
            print(f"  [{sym}] skipped: {exc}")
            continue
        all_ok &= compare(sym, bf)

    print("\nALL OK" if all_ok else "\nMISMATCHES FOUND")
