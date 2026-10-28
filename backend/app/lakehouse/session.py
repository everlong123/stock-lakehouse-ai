"""Canonical daily-session normalisation for the Silver layer.

Why this module exists
----------------------
The lakehouse is single-interval: only daily bars are ever read back. But
Bronze accumulates several kinds of rows per trading day:

  * the **session bar**, stamped at the exchange OPEN (13:30 UTC for the NYSE
    in EDT, 14:30 UTC in EST; 02:00 UTC for HOSE);
  * the **settled bar** for the same session, stamped at the exchange CLOSE
    (20:00 UTC). Yahoo serves the current day at its close stamp, so a symbol
    refreshed during a session keeps a second copy of that day forever;
  * genuine **intraday ticks** - ``vn_rest`` one-minute prints for
    Vietnamese symbols, or manually injected ``manual`` rows.

Three defects follow, and all three are visible in the web UI:

  1. **Two candles for one trading day.** The 13:30 and the 20:00 copy both
     survive because their payloads differ slightly (Yahoo reports the
     settled bar's open as 349.11 where the open-stamped copy says 349.12,
     and the volumes differ by ~0.1%). The chart draws a jump that never
     happened, and every rolling window counts the session twice - which
     shifts SMA/RSI/MACD and outright breaks the argmax-based indicators
     (Aroon, Stochastic, Williams %R, CCI), because a repeated value moves
     the extremum inside the window.

  2. **A hundred candles for one day.** VCB 2026-10-23 carries 101
     ``vn_rest`` one-minute rows. The daily chart becomes an unreadable
     smear and the day's "close" is whatever the last tick happened to be.

  3. **A false crash.** AAPL 2026-10-13 carries 13 ``manual`` ticks around
     close=333.9 sitting next to the real session close of 341.27, so the
     chart draws a ~2% drop that never occurred.

What this module does
----------------------
It produces exactly ONE bar per trading day per symbol:

  * when the day has a canonical session bar, that bar wins and the other
    rows for that day are dropped;
  * when the day has only intraday rows, they are **aggregated** into a
    daily bar (open = first, high = max, low = min, close = last,
    volume = sum), so the information is preserved rather than discarded.

Nothing is invented: a day with no rows produces no bar, and a day whose
rows are all unusable produces no bar either.

A note on the session stamp
---------------------------
The same session is stamped 13:30 UTC in EDT (summer) and 14:30 UTC in EST
(winter), because Yahoo expresses the exchange open in UTC. That is CORRECT
and is deliberately preserved: a single symbol's series legitimately contains
both stamps, and the year-over-year counts confirm it (166 EDT days and 85
EST days per year - the exact ratio of the two halves of a trading year).
Normalising it away would misalign every bar against its own market open.
"""

from __future__ import annotations

import pandas as pd

#: Sources whose rows are DAILY session bars. Everything else (manual, kafka,
#: vn_ws, vn_rest, finnhub_ws, ...) is treated as an intraday observation.
DAILY_BAR_SOURCES = frozenset(
    {
        "yahoo_http",
        "yfinance",
        "yfinance_python",
        "yfinance_eod",
        "stooq",
        "alpha_vantage",
        "web_scraper",
        "multi_source",
    }
)

#: Columns that make up a bar's payload.
PRICE_COLUMNS = ("open", "high", "low", "close")

#: Columns whose value is carried over to the surviving bar.
_CARRY_COLUMNS = ("adj_close", "volume")


def _is_daily_bar_source(source: object) -> bool:
    """True when the row's source produces whole-session bars."""
    if source is None or (isinstance(source, float) and pd.isna(source)):
        return False
    return str(source).strip().lower() in DAILY_BAR_SOURCES


def _modal_stamp(stamps: pd.Series) -> str | None:
    """The symbol's dominant time-of-day, breaking ties deterministically.

    The tiebreak matters: on a frame where two stamps each appear once,
    ``value_counts().index[0]`` returns whichever came first, so the result
    would depend on row order. The exchange open is preferred, because that
    is what the overwhelming majority of historical bars use.
    """
    counts = stamps.value_counts()
    if counts.empty:
        return None
    top = counts[counts == counts.max()].index.tolist()
    if len(top) == 1:
        return top[0]
    for preferred in ("13:30", "14:30", "02:00", "20:00"):
        if preferred in top:
            return preferred
    return sorted(top)[0]


def _aggregate_intraday(group: pd.DataFrame) -> dict:
    """Fold a day's intraday rows into one daily bar."""
    ordered = group.sort_values("timestamp")
    first = ordered.iloc[0]
    last = ordered.iloc[-1]

    bar: dict = {
        "open": float(first["open"]),
        "high": float(pd.to_numeric(ordered["high"], errors="coerce").max()),
        "low": float(pd.to_numeric(ordered["low"], errors="coerce").min()),
        "close": float(last["close"]),
    }
    volume = pd.to_numeric(ordered["volume"], errors="coerce")
    bar["volume"] = float(volume.sum()) if volume.notna().any() else 0.0

    if "adj_close" in ordered.columns:
        adj = pd.to_numeric(ordered["adj_close"], errors="coerce").dropna()
        bar["adj_close"] = float(adj.iloc[-1]) if not adj.empty else bar["close"]
    else:
        bar["adj_close"] = bar["close"]
    return bar


def canonicalize_daily_sessions(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Collapse a symbol's rows to one bar per trading day.

    Args:
        frame: A frame with at least ``timestamp``, ``open``, ``high``,
            ``low``, ``close``. ``source`` and ``volume`` are used when
            present.

    Returns:
        ``(canonical_frame, report)`` where ``report`` counts what happened,
        so the Silver quality report can surface it instead of hiding it.
    """
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

    # The symbol's dominant stamp across ALL its rows, used to stamp the
    # aggregated intraday bars so they line up with the session bars.
    symbol_stamp = _modal_stamp(working["_stamp"])
    working["_symbol_stamp"] = symbol_stamp

    # Group by (symbol, trading day): a trading day is only unique WITHIN a
    # symbol. Grouping by the day alone would collapse AAPL's session into
    # MSFT's, silently deleting a whole symbol from the batch.
    if "symbol" in working.columns:
        group_keys = ["symbol", "_day"]
    else:
        group_keys = ["_day"]

    kept_rows: list[pd.Series] = []
    aggregated_rows: list[pd.Series] = []

    for _group_key, day_frame in working.groupby(group_keys, sort=True):
        report["days_in"] += 1
        daily = day_frame[day_frame["_is_daily_bar"]]
        intraday = day_frame[~day_frame["_is_daily_bar"]]

        if not daily.empty:
            # Prefer the row whose stamp matches the symbol's convention, so
            # the series keeps a uniform timestamp. Among rows with that
            # stamp the most recently ingested one wins.
            daily = daily.copy()
            daily["_matches"] = daily["_stamp"] == symbol_stamp
            if "ingestion_time" in daily.columns:
                daily["_ingest"] = pd.to_datetime(daily["ingestion_time"], utc=True, errors="coerce")
            else:
                daily["_ingest"] = pd.Timestamp("1970-01-01", tz="UTC")
            daily = daily.sort_values(
                ["_matches", "_ingest"], ascending=[False, False], kind="mergesort"
            )
            survivor = daily.iloc[0]
            kept_rows.append(survivor)
            # Everything else on that day - the re-stamped session copy and
            # any intraday ticks - is redundant for a daily series.
            dropped = len(day_frame) - 1
            report["duplicate_session_rows_dropped"] += dropped
            continue

        # Only intraday rows for this day: aggregate them into one bar.
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
        # Stamp the aggregated bar with the symbol's session stamp so it
        # lines up with the neighbouring daily bars. The YEAR and MONTH must
        # come from the day being aggregated - taking them from the frame's
        # first row would move a December day into January.
        if symbol_stamp:
            hour, _, minute = symbol_stamp.partition(":")
            day_value = pd.Timestamp(day_frame["_day"].iloc[0])
            try:
                row["timestamp"] = pd.Timestamp(
                    year=day_value.year,
                    month=day_value.month,
                    day=day_value.day,
                    hour=int(hour),
                    minute=int(minute),
                    tz="UTC",
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
    # Keep the original column order so downstream writers see a stable schema.
    original_columns = [c for c in frame.columns if c in out.columns]
    out = out.loc[:, original_columns + [c for c in out.columns if c not in original_columns]]

    report["rows_out"] = int(len(out))
    report["days_out"] = int(out["timestamp"].dt.date.nunique())
    return out, report
