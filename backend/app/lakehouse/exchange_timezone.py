"""The exchange timezone of a symbol, and the trading day a bar belongs to.

WHY THIS EXISTS
---------------
The lakehouse stores every bar in UTC and groups rows into trading days by
the UTC calendar date. That is correct for every market whose session OPENS
after 00:00 UTC - the NYSE opens at 13:30/14:30 UTC, the HOSE at 02:00 UTC,
the HKEX at 01:30 UTC, the TSE at 00:00 UTC.

It is WRONG for a market whose session opens BEFORE 00:00 UTC. The ASX opens
at 10:00 Sydney time, which is 23:00 UTC on the PREVIOUS calendar day
(22:00 UTC in the southern winter). So the bar Yahoo stamps
``2026-11-11 23:00Z`` describes the trading session of **2026-11-12**, not of
2026-11-11.

Grouping such bars by their UTC date splits ONE trading session across TWO
calendar days, and the second half - the after-close quote the same provider
publishes for that same session - lands on the NEXT UTC day, right next to
the next session's own daily bar. The lakehouse then holds two rows for one
trading day, one of them a synthetic aggregate of intraday quotes, and the
layers disagree about which close belongs to which day.

THE MEASUREMENT (15/11/2026)
---------------------------
All 19 ``.AX`` symbols in the universe failed the quality gate's
layer-agreement check, and every one of them failed on exactly one session -
2026-11-12 - where Bronze reported 170.87 (the after-close quote of the
13th) and Silver reported 171.76 (the real close of the 12th). The live
provider confirmed 171.76 for that session.

THE FIX
-------
Derive the trading day in the EXCHANGE's timezone, for the exchanges whose
session crosses UTC midnight, and keep the UTC day everywhere else. The table
below is deliberately short: it lists only the exchanges whose session opens
before 00:00 UTC. Every other market keeps the UTC day it already used, so
this change cannot move a session for the 983 symbols that do not need it.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

#: Exchanges whose trading session OPENS BEFORE 00:00 UTC, i.e. the bar's UTC
#: calendar day is one day EARLIER than the session's real-world date.
#:
#: The key is the Yahoo-style ticker suffix. The value is the IANA timezone
#: the exchange keeps its wall clock in.
#:
#: Only these two exchanges appear in this universe (19 ``.AX`` symbols). The
#: list is intentionally NOT a full exchange registry: a market whose session
#: opens after 00:00 UTC is already handled correctly by the UTC day, and
#: listing it here would only add risk.
CROSS_UTC_MIDNIGHT_EXCHANGES: dict[str, str] = {
    ".AX": "Australia/Sydney",
    ".NZ": "Pacific/Auckland",
}


def exchange_timezone(symbol: Any) -> str | None:
    """The IANA timezone of the exchange that trades ``symbol``.

    Returns ``None`` when the exchange's session does not cross UTC midnight,
    which means the UTC calendar day of a bar IS its trading day and no
    timezone conversion is needed.
    """
    if symbol is None:
        return None
    text = str(symbol).strip().upper()
    if not text:
        return None
    for suffix, tz_name in CROSS_UTC_MIDNIGHT_EXCHANGES.items():
        if text.endswith(suffix):
            return tz_name
    return None


def session_day_of(timestamp: Any, symbol: Any = None) -> date | None:
    """The trading day ``timestamp`` belongs to, for ``symbol``'s exchange.

    For an exchange whose session crosses UTC midnight this is the LOCAL
    calendar date; for every other exchange it is the UTC calendar date.
    """
    if timestamp is None:
        return None
    try:
        stamp = pd.Timestamp(timestamp)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    tz_name = exchange_timezone(symbol)
    if tz_name is None:
        return stamp.date()
    try:
        return stamp.tz_convert(tz_name).date()
    except Exception:  # noqa: BLE001 - an unknown zone falls back to UTC
        return stamp.date()


def session_days(working: pd.DataFrame) -> pd.Series:
    """The trading day of every row of ``working``.

    ``working`` must carry a UTC-aware ``timestamp`` column. When it also
    carries a ``symbol`` column, each row's day is derived in its own
    exchange's timezone; otherwise the UTC day is used.
    """
    days = working["timestamp"].dt.date
    if "symbol" not in working.columns:
        return days

    symbols = working["symbol"].astype(str)
    days = days.copy()
    for suffix, tz_name in CROSS_UTC_MIDNIGHT_EXCHANGES.items():
        mask = symbols.str.endswith(suffix, na=False)
        if not bool(mask.any()):
            continue
        local = working.loc[mask, "timestamp"].dt.tz_convert(tz_name)
        days.loc[mask] = local.dt.date
    return days
