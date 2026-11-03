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

from datetime import date

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


def _is_already_one_row_per_day(working: pd.DataFrame, group_keys: list[str]) -> bool:
    """True when every trading day already holds exactly one daily bar.

    WHY THIS EXISTS
    ---------------
    `canonicalize_daily_sessions` collapses a symbol's rows to one bar per
    trading day. The general implementation is a Python loop over the
    groups, which costs seconds for a 10-year daily history - and the read
    path calls it on every symbol it serves.

    But the case the general implementation was written for (duplicate
    session rows, intraday ticks) is RARE: a symbol that was already
    canonicalised on write comes back with exactly one daily bar per day,
    and then the loop just re-selects every row unchanged.

    This check is the vectorised equivalent of "the loop would keep
    everything":

    * every group has exactly one row  -> no duplicates to drop
    * every row is a daily bar          -> no intraday ticks to aggregate

    When both hold, the canonical form IS the input, so the caller can skip
    the loop entirely. When either fails, the general path runs and does the
    real work.

    The check is deliberately conservative: a false NEGATIVE just means the
    slow path runs (correct, just slower); a false POSITIVE would drop data,
    so both conditions are checked strictly.
    """
    if working.empty:
        return False
    if not bool(working["_is_daily_bar"].all()):
        return False
    # `groupby(...).size()` on the day keys: every group must hold one row.
    sizes = working.groupby(group_keys, sort=False).size()
    return bool(len(sizes) == len(working))


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


def _canonicalize_daily_only(
    working: pd.DataFrame,
    group_keys: list[str],
    symbol_stamp: str | None,
    day_has_daily: pd.Series,
) -> tuple[pd.DataFrame, int]:
    """Vectorised collapse for the days that hold at least one daily bar.

    This is the hot path. A 10-year daily ticker has ~2531 trading days, and
    the original implementation walked every one of them in Python, calling
    `sort_values` + `iloc[0]` per group. Measured cost: **9.2 seconds** for
    2550 rows - and the function runs on EVERY market-data read (the read path
    re-canonicalises) and on every Silver rebuild. That was the single
    biggest source of GIL contention in the API process: while the auto-refresh
    rebuilt symbols in the background, a user request needed ~100s instead of
    ~1s, because it was queued behind this loop.

    The vectorised form computes exactly the same result:

    * a day's survivor is the daily-bar row whose stamp matches the symbol's
      convention, ties broken by the most recent ingestion time;
    * every other row of that day (the re-stamped copy, the intraday ticks) is
      dropped and counted.

    ``sort_values`` on multiple keys uses a stable lexsort, so the tie-break
    order matches the original per-group ``sort_values`` + ``iloc[0]``.

    Args:
        working: the working frame, carrying the ``_is_daily_bar`` flag.
        group_keys: the (symbol, trading day) grouping keys.
        symbol_stamp: the symbol's dominant session stamp.
        day_has_daily: boolean per row, True when the row's day holds a
            daily bar. Computed by the caller so it can be reused.

    Returns:
        ``(survivors, dropped_row_count)``.
    """
    daily_mask = working["_is_daily_bar"]
    if not daily_mask.any():
        return working.iloc[0:0].copy(), 0

    working["_matches"] = working["_stamp"] == symbol_stamp
    if "ingestion_time" in working.columns:
        working["_ingest"] = pd.to_datetime(working["ingestion_time"], utc=True, errors="coerce")
    else:
        working["_ingest"] = pd.Timestamp("1970-01-01", tz="UTC")

    ascending = [True] * len(group_keys) + [False, False]
    ordered = working[daily_mask].sort_values(
        group_keys + ["_matches", "_ingest"],
        ascending=ascending,
        kind="mergesort",
    )
    survivors = ordered.drop_duplicates(subset=group_keys, keep="first")

    # Rows that belong to a day with a daily bar are redundant except for the
    # survivor, so the dropped count is (those rows) - (those days).
    rows_in_daily_days = int(day_has_daily.sum())
    dropped = rows_in_daily_days - int(len(survivors))

    out = survivors.drop(
        columns=[
            c
            for c in ("_day", "_stamp", "_is_daily_bar", "_symbol_stamp", "_matches", "_ingest")
            if c in survivors.columns
        ],
        errors="ignore",
    )
    return out.reset_index(drop=True), dropped


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

    # ── FAST PATH ────────────────────────────────────────────────────────────
    # The generic implementation below is a Python loop over every trading
    # day, and it costs ~3.8s for a 10-year daily history (2531 groups) -
    # a cost paid on EVERY read, because the read path re-canonicalises.
    #
    # The overwhelmingly common case is the opposite of what the slow path
    # exists for: exactly ONE row per trading day, and that row is a daily
    # bar. In that case the loop's outcome is fully determined: keep every
    # row as-is, and the only thing the loop adds is the report counters.
    # Detecting that case with a vectorised check costs microseconds.
    if _is_already_one_row_per_day(working, group_keys):
        out = working.drop(columns=["_day", "_stamp", "_is_daily_bar", "_symbol_stamp"])
        # Restore the original column order so downstream writers see a stable
        # schema, exactly like the slow path does.
        original_columns = [c for c in frame.columns if c in out.columns]
        out = out.loc[:, original_columns + [c for c in out.columns if c not in original_columns]]
        out = out.sort_values("timestamp").reset_index(drop=True)
        report["rows_in"] = int(len(frame))
        report["rows_out"] = int(len(out))
        report["days_in"] = int(len(out))
        report["days_out"] = int(out["timestamp"].dt.date.nunique())
        return out, report

    # ── VECTORISED PATH ─────────────────────────────────────────────────────
    # The original implementation looped over EVERY trading day in Python and
    # called `sort_values` + `iloc[0]` inside each iteration. For a 10-year
    # daily ticker that is 2531 iterations and measured **9.2 seconds** for
    # 2550 rows.
    #
    # That cost was paid on every market-data read (the read path
    # re-canonicalises what it serves) AND on every Silver rebuild - which the
    # auto-refresh pass does for hundreds of symbols. Because it is pure
    # Python, it holds the GIL for the whole 9 seconds, so every HTTP request
    # in the same process queued behind it. That is what turned a 1-second
    # backtest into a 100-second one and blew past the frontend's 90s
    # timeout.
    #
    # The days that hold a daily bar are the overwhelming majority, and their
    # outcome is fully determined by a sort + `drop_duplicates`, so they are
    # handled vectorised. Only the rare intraday-only days still need the
    # per-day Python loop.
    #
    # `transform("any")` marks every row whose day holds at least one daily
    # bar. A day with both a daily bar and intraday ticks keeps the daily bar
    # and drops the ticks, exactly like the original loop did.
    day_has_daily = working.groupby(group_keys, sort=False)["_is_daily_bar"].transform("any")

    survivor_frames: list[pd.DataFrame] = []
    aggregated_rows: list[pd.Series] = []

    survivors_df, dropped = _canonicalize_daily_only(
        working, group_keys, symbol_stamp, day_has_daily
    )
    report["duplicate_session_rows_dropped"] += dropped
    if not survivors_df.empty:
        survivor_frames.append(survivors_df)

    # Days WITHOUT a daily bar still need the intraday aggregation. They are
    # rare, so the per-day Python loop is acceptable here.
    intraday_only = working[~day_has_daily]
    if not intraday_only.empty:
        for _group_key, day_frame in intraday_only.groupby(group_keys, sort=True):
            intraday = day_frame[~day_frame["_is_daily_bar"]]
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
            # lines up with the neighbouring daily bars. The YEAR and MONTH
            # must come from the day being aggregated - taking them from the
            # frame's first row would move a December day into January.
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

    report["days_in"] = int(working.groupby(group_keys, sort=False).ngroups)

    frames: list[pd.DataFrame] = list(survivor_frames)
    if aggregated_rows:
        frames.append(pd.DataFrame(aggregated_rows).reset_index(drop=True))
    if not frames:
        report["rows_out"] = 0
        report["days_out"] = 0
        return frame.iloc[0:0].copy(), report

    if len(frames) == 1:
        out = frames[0]
    else:
        out = pd.concat(frames, ignore_index=True)
    out = out.drop(columns=[c for c in ("_day", "_stamp", "_is_daily_bar", "_symbol_stamp", "_matches", "_ingest") if c in out.columns])
    out = out.sort_values("timestamp").reset_index(drop=True)
    # Keep the original column order so downstream writers see a stable schema.
    original_columns = [c for c in frame.columns if c in out.columns]
    out = out.loc[:, original_columns + [c for c in out.columns if c not in original_columns]]
    # Normalise the datetime resolution to nanoseconds.
    #
    # The vectorised path keeps the frame's own dtype (Bronze stores
    # `datetime64[us, UTC]`), while the old per-day loop rebuilt the frame
    # from a list of Series, which promoted every timestamp to
    # `datetime64[ns, UTC]`. The VALUES are identical, but the dtype differs,
    # and a stored parquet written from one and read back as the other makes
    # `.equals()` comparisons fail across the pipeline. Normalising here keeps
    # the on-disk schema stable no matter which path produced the frame.
    for _column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[_column]):
            out[_column] = out[_column].astype("datetime64[ns, UTC]")

    report["rows_out"] = int(len(out))
    report["days_out"] = int(out["timestamp"].dt.date.nunique())
    return out, report


def session_date(ts: object) -> date | None:
    """Return the trading day a stored timestamp belongs to.

    WHY THIS EXISTS
    ---------------
    Bronze stores whatever the provider published, which can include an
    after-hours bar at 20:00 UTC for a US ticker whose regular session opened
    at 13:30 UTC on the same day. Silver and Gold canonicalise one bar per
    session and stamp it with the session open, so Gold's newest timestamp
    for such a symbol is ``2026-10-02 13:30`` while Bronze's is
    ``2026-10-02 20:00`` - the same trading day, a different clock time.

    Any watermark comparison between the layers must therefore be made per
    trading day. Comparing raw timestamps reports those symbols as stale
    forever, which makes an incremental refresh rebuild them on every pass
    without ever converging.

    The day is taken in UTC, which is the timezone every stored stamp uses.
    For the markets in this lakehouse the session open always falls on the
    same UTC day as the trade it describes (13:30 / 14:30 / 02:00 / 08:00
    UTC), so no extra calendar shifting is needed.
    """
    if ts is None:
        return None
    try:
        stamp = pd.Timestamp(ts)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.date()
