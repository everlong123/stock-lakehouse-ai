"""Shared helpers for turning fetch boundaries into provider request bounds.

Why this module exists
----------------------
Every provider converts the ``start``/``end`` it is handed into a Unix
timestamp (or a calendar date) and sends that upstream. When the caller
passes a NAIVE datetime, ``datetime.timestamp()`` interprets it in the
MACHINE'S local timezone. The lakehouse stores every bar in UTC, so that
conversion shifts the request window by the host's UTC offset.

The shift is not cosmetic. A daily bar for a trading session is stamped at
the exchange's open in UTC - 13:30 UTC for the NYSE in EDT, 14:30 UTC in
EST, 02:00 UTC for HOSE. A boundary that lands a few hours past the open
therefore excludes that session's bar entirely, and the day disappears from
the response with no error. Measured on this project: 358 symbols were
missing 2026-10-21 while 489 of their peers had it.

The rule is therefore: a naive boundary is interpreted as UTC, matching how
the lakehouse stores and compares every timestamp. Aware boundaries are
converted to UTC.
"""

from __future__ import annotations

from datetime import date, datetime, timezone


def as_utc(value: datetime | None) -> datetime | None:
    """Return ``value`` as an aware UTC datetime, treating naive input as UTC.

    ``None`` passes through so callers can use ``as_utc(x) or default``.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_unix(value: datetime | None) -> int | None:
    """Return the Unix timestamp of ``value``, treating naive input as UTC."""
    coerced = as_utc(value)
    return None if coerced is None else int(coerced.timestamp())


def to_date_str(value: datetime | None, fmt: str = "%Y-%m-%d") -> str | None:
    """Format ``value`` as a calendar date string, treating naive input as UTC.

    Providers that speak in dates (Stooq's ``d1``/``d2``) have no notion of
    a time of day, so the boundary is normalised to the UTC calendar day.
    """
    coerced = as_utc(value)
    return None if coerced is None else coerced.strftime(fmt)


def to_ymd(value: datetime | None) -> str | None:
    """Return ``value`` as ``YYYYMMDD`` (Stooq's format), naive input = UTC."""
    return to_date_str(value, "%Y%m%d")


def utc_today() -> date:
    """Today's date in UTC."""
    return datetime.now(timezone.utc).date()
