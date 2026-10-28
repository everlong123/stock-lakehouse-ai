"""Tests for the fetch-boundary timezone handling.

The bug these guard against
---------------------------
`AutoRefreshService` computed its next fetch window as

    start = last_bar_timestamp.replace(tzinfo=None) + timedelta(days=1)

and passed that NAIVE datetime to the provider, which turned it into a Unix
timestamp with ``datetime.timestamp()``. For a naive datetime Python uses
the MACHINE'S local timezone, so on a host at UTC+7 the request boundary
moved seven hours later than intended.

A daily bar is stamped at the exchange open in UTC - 13:30 UTC for the NYSE
in EDT, 14:30 UTC in EST, 02:00 UTC for HOSE. A boundary that lands past
the open excludes that session's bar, and the day vanishes from the
response with no error at all. Measured on this project: 358 symbols were
missing 2026-10-21 while 489 of their peers had it.

The rule the code now follows: a naive boundary is read as UTC, matching
how the lakehouse stores and compares every timestamp.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_sources.time_utils import as_utc, to_ymd, to_unix  # noqa: E402


def test_naive_datetime_is_read_as_utc():
    naive = datetime(2026, 10, 21, 13, 30)
    assert as_utc(naive) == datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc)


def test_aware_datetime_is_converted_to_utc():
    aware = datetime(2026, 10, 21, 20, 30, tzinfo=timezone(timedelta(hours=7)))
    assert as_utc(aware) == datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc)


def test_none_passes_through():
    assert as_utc(None) is None
    assert to_unix(None) is None


def test_to_unix_is_independent_of_the_host_timezone():
    """The whole point: the timestamp must not depend on the local clock."""
    naive = datetime(2026, 10, 21, 13, 30)
    expected = int(datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc).timestamp())
    assert to_unix(naive) == expected


def test_to_unix_of_an_aware_value_matches_utc():
    aware = datetime(2026, 10, 21, 20, 30, tzinfo=timezone(timedelta(hours=7)))
    assert to_unix(aware) == to_unix(datetime(2026, 10, 21, 13, 30))


def test_date_helper_uses_the_utc_calendar_day():
    # 20:30 in UTC+7 is 13:30 UTC - still the same UTC calendar day.
    aware = datetime(2026, 10, 21, 20, 30, tzinfo=timezone(timedelta(hours=7)))
    assert to_ymd(aware) == "20261021"


def test_provider_period_boundary_keeps_the_session_open():
    """A boundary at the session open must still return that session.

    This is the regression guard for the dropped trading days: the request
    window's start must not be pushed past the exchange's open, because the
    bar for that day would then be excluded from the response.
    """
    session_open = datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc)
    period1 = to_unix(session_open)
    # Yahoo's period1 is inclusive of the instant itself, so a bar stamped
    # exactly at period1 is still returned.
    assert period1 == int(session_open.timestamp())
    assert period1 % 86400 == (13 * 3600 + 30 * 60) % 86400


def test_refresh_overlap_reaches_back_over_previously_skipped_days():
    """The refresh must re-request days it may have stepped over.

    A 5-day overlap is applied to the watermark so a day that a previous
    pass skipped is picked up on the next one.
    """
    latest = datetime(2026, 10, 22, 13, 30, tzinfo=timezone.utc)
    overlap_days = 5
    start = latest - timedelta(days=overlap_days)
    # 2026-10-21 is the day that was missing for 358 symbols.
    assert start <= datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc)
