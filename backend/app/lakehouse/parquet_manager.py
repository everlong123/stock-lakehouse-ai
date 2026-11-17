"""Parquet partition helpers for the medallion layers."""

from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd


def partition_relative_path(symbol: str, timestamp: datetime, filename: str = "part-001.parquet") -> str:
    """Build a Hive-style partition path: symbol=AAPL/year=2026/month=09/part-001.parquet."""
    year = int(timestamp.year)
    month = int(timestamp.month)
    return f"symbol={symbol.upper()}/year={year}/month={month:02d}/{filename}"


def add_partition_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Add year/month partition columns from timestamp."""
    result = frame.copy()
    ts = pd.to_datetime(result["timestamp"], utc=True)
    result["year"] = ts.dt.year.astype(int)
    result["month"] = ts.dt.month.astype(int)
    return result


def split_by_partition(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Group rows by symbol/year/month partition path."""
    partitioned = add_partition_columns(frame)
    grouped: dict[str, pd.DataFrame] = {}
    for (symbol, year, month), group in partitioned.groupby(["symbol", "year", "month"], sort=True):
        path = f"symbol={symbol}/year={int(year)}/month={int(month):02d}/part-001.parquet"
        grouped[path] = group.reset_index(drop=True)
    return grouped


#: The shape of a partition key: ``.../year=2026/month=09/part-001.parquet``.
_PARTITION_PATTERN = re.compile(r"year=(?P<year>\d{4})/month=(?P<month>\d{1,2})/")


def partition_month(key: str) -> tuple[int, int] | None:
    """The (year, month) a partition key holds, or None when it has none.

    A key that does not carry a year/month pair - an object written
    outside the partitioned layout - returns None, and the caller then
    keeps it, because a key it cannot place is safer to read than to
    skip.
    """
    match = _PARTITION_PATTERN.search(key)
    if match is None:
        return None
    return int(match.group("year")), int(match.group("month"))


def filter_keys_by_window(
    keys: list[str],
    since: date | None = None,
    until: date | None = None,
) -> list[str]:
    """The partition keys that can hold rows inside a date window.

    WHY THIS EXISTS
    ---------------
    A ten-year daily symbol is stored as ~121 monthly partitions. A
    request for "the last six months" needs six of them, and the other
    115 are downloaded, parsed and discarded. The request cost was
    therefore set by the symbol's HISTORY rather than by the window the
    caller asked for.

    A partition is kept when its month can OVERLAP the window: the
    window's first month and its last month are both kept, because a
    session near a month boundary can still be stamped inside the
    neighbouring partition.

    A key without a recognisable year/month pair is always kept. Not
    being able to place a key is a reason to read it, not to skip it -
    skipping it would silently drop real rows.
    """
    if since is None and until is None:
        return list(keys)

    first = (since.year, since.month) if since is not None else None
    last = (until.year, until.month) if until is not None else None

    kept: list[str] = []
    for key in keys:
        placed = partition_month(key)
        if placed is None:
            kept.append(key)
            continue
        if first is not None and placed < first:
            continue
        if last is not None and placed > last:
            continue
        kept.append(key)
    return kept


def partitions_from(
    partitions: dict[str, pd.DataFrame],
    changed_since: date | None,
) -> dict[str, pd.DataFrame]:
    """The partitions a rebuild has to write, given when the data changed.

    WHY THIS EXISTS
    ---------------
    Every feature in Silver and Gold is CAUSAL: a rolling mean, an
    exponential average and a session canonicalisation all look BACKWARD
    only. So a rebuild triggered by a new bar at the END of the history
    produces EXACTLY the same rows for every earlier session - the new
    bar cannot change a value that was computed without it.

    Writing all ~121 monthly partitions anyway is therefore wasted
    work: 2.7 s of MinIO round-trips per symbol, measured 14/11/2026,
    of which the useful part is one or two partitions.

    `changed_since` is the EARLIEST session whose content may have
    changed. Every partition from that month onwards is written; the
    earlier ones are left alone because their content is unchanged.

    Passing None writes everything, which is what a full backfill and
    any rebuild without a known change date must do.
    """
    if changed_since is None:
        return partitions

    first = (changed_since.year, changed_since.month)
    kept: dict[str, pd.DataFrame] = {}
    for path, frame in partitions.items():
        placed = partition_month(path)
        if placed is None or placed >= first:
            kept[path] = frame
    return kept
