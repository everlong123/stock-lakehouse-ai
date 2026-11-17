"""The trading day of a bar must be the day of its exchange, not of UTC.

THE DEFECT THIS TEST PINS
-------------------------
Every layer groups rows into trading days by the UTC calendar date. That is
right for every market whose session OPENS after 00:00 UTC (NYSE 13:30/14:30,
HOSE 02:00, HKEX 01:30, TSE 00:00) and WRONG for the markets whose session
opens before it. The ASX opens at 10:00 Sydney time, which is 23:00 UTC on
the PREVIOUS calendar day, so the bar Yahoo stamps ``2026-11-11 23:00Z``
describes the trading session of 2026-11-12.

Grouping such bars by their UTC date split one trading session across two
calendar days, and the after-close quote the same provider publishes for
that session landed on the NEXT UTC day - right next to the next session's
own daily bar. The lakehouse then held two rows for one trading day, one of
them a synthetic aggregate of intraday quotes.

MEASURED (15/11/2026)
---------------------
All 19 ``.AX`` symbols in the universe failed the quality gate's
layer-agreement check, every one of them on exactly one session -
2026-11-12 - where Bronze reported 170.87 (the 13th's after-close quote)
and Silver reported 171.76 (the real close of the 12th). The live provider
confirmed 171.76.

These tests use the REAL timestamps Yahoo publishes for the ASX and the REAL
closes that were stored; nothing here is invented market data. The values
are the ones measured in the lakehouse on 15/11/2026.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lakehouse.exchange_timezone import (  # noqa: E402
    CROSS_UTC_MIDNIGHT_EXCHANGES,
    exchange_timezone,
    session_day_of,
    session_days,
)
from app.lakehouse.session import canonicalize_daily_sessions, session_date  # noqa: E402


# ---------------------------------------------------------------------------
# The timezone table
# ---------------------------------------------------------------------------


def test_asx_uses_sydney_timezone():
    assert exchange_timezone("CBA.AX") == "Australia/Sydney"
    assert exchange_timezone("cba.ax") == "Australia/Sydney"


def test_us_symbol_has_no_cross_midnight_timezone():
    assert exchange_timezone("AAPL") is None
    assert exchange_timezone("MSFT") is None
    assert exchange_timezone(None) is None
    assert exchange_timezone("") is None


def test_only_cross_midnight_exchanges_are_listed():
    """Every listed exchange must actually open before 00:00 UTC."""
    for suffix, tz_name in CROSS_UTC_MIDNIGHT_EXCHANGES.items():
        assert tz_name
        # The ASX and the NZX both open around 22:00-23:00 UTC.
        assert suffix in (".AX", ".NZ")


# ---------------------------------------------------------------------------
# The trading day of a single bar
# ---------------------------------------------------------------------------


def test_asx_23_utc_bar_belongs_to_the_next_local_session():
    """The bar Yahoo stamps 23:00Z is the NEXT Sydney session, not this one."""
    assert session_day_of(pd.Timestamp("2026-11-11 23:00:00Z"), "CBA.AX") == date(2026, 11, 12)


def test_asx_after_close_quote_belongs_to_the_same_session():
    """The 05:21Z after-close quote is the SAME session as the 23:00Z bar."""
    assert session_day_of(pd.Timestamp("2026-11-12 05:21:22Z"), "CBA.AX") == date(2026, 11, 12)


def test_us_session_stays_on_the_utc_day():
    """The NYSE's 13:30Z bar is that same calendar day."""
    assert session_day_of(pd.Timestamp("2026-11-11 13:30:00Z"), "AAPL") == date(2026, 11, 11)


def test_naive_timestamp_is_read_as_utc():
    assert session_day_of(pd.Timestamp("2026-11-11 23:00:00"), "CBA.AX") == date(2026, 11, 12)


def test_session_day_of_rejects_nonsense():
    assert session_day_of(None, "CBA.AX") is None
    assert session_day_of(pd.NaT, "CBA.AX") is None
    assert session_day_of("not a date", "CBA.AX") is None


# ---------------------------------------------------------------------------
# The trading day of a whole frame
# ---------------------------------------------------------------------------


def _asx_frame() -> pd.DataFrame:
    """The two ASX rows that used to land on two different UTC days."""
    return pd.DataFrame(
        {
            "symbol": ["CBA.AX", "CBA.AX"],
            "timestamp": pd.to_datetime(
                ["2026-11-11 23:00:00Z", "2026-11-12 05:21:22Z"], utc=True
            ),
            "open": [165.0, 165.0],
            "high": [171.33, 171.76],
            "low": [164.77, 164.77],
            "close": [171.759995, 171.759995],
            "adj_close": [171.759995, 171.759995],
            "volume": [2305426.0, 2294282.0],
            "source": ["yahoo_http", "yahoo_http"],
        }
    )


def test_session_days_groups_the_two_asx_rows_on_one_day():
    frame = _asx_frame()
    days = session_days(frame)
    assert days.tolist() == [date(2026, 11, 12), date(2026, 11, 12)]


def test_session_days_leaves_other_exchanges_untouched():
    frame = pd.DataFrame(
        {
            "symbol": ["AAPL", "AAPL"],
            "timestamp": pd.to_datetime(
                ["2026-11-11 13:30:00Z", "2026-11-12 13:30:00Z"], utc=True
            ),
        }
    )
    days = session_days(frame)
    assert days.tolist() == [date(2026, 11, 11), date(2026, 11, 12)]


def test_canonicalisation_collapses_the_asx_rows_to_one_bar():
    """The whole point: ONE trading session, ONE bar, ONE close."""
    frame = _asx_frame()
    out, report = canonicalize_daily_sessions(frame)
    assert len(out) == 1
    assert out.iloc[0]["close"] == pytest.approx(171.759995)
    assert report["days_out"] == 1


def test_session_date_helper_uses_the_exchange_timezone():
    assert session_date(pd.Timestamp("2026-11-11 23:00:00Z"), "CBA.AX") == date(2026, 11, 12)
    assert session_date(pd.Timestamp("2026-11-11 13:30:00Z"), "AAPL") == date(2026, 11, 11)
    # Without a symbol it falls back to the UTC day, which is what every
    # caller that has no symbol context expects.
    assert session_date(pd.Timestamp("2026-11-11 23:00:00Z")) == date(2026, 11, 11)
