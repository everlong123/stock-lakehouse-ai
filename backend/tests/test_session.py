"""Tests for the daily-session canonicalisation.

Run with:  python3 -m pytest backend/tests/test_session.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lakehouse.session import canonicalize_daily_sessions  # noqa: E402


def _row(ts: str, close: float, source: str, volume: float = 100.0, **extra) -> dict:
    row = {
        "symbol": "AAPL",
        "timestamp": pd.Timestamp(ts, tz="UTC"),
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": volume,
        "source": source,
    }
    row.update(extra)
    return row


def test_single_session_bar_is_untouched():
    frame = pd.DataFrame([_row("2026-10-20 13:30", 341.27, "yahoo_http")])
    out, report = canonicalize_daily_sessions(frame)
    assert len(out) == 1
    assert report["duplicate_session_rows_dropped"] == 0
    assert out.iloc[0]["close"] == 341.27


def test_restamped_session_copy_is_dropped():
    """The settled 20:00 copy of a session must not become a second candle."""
    frame = pd.DataFrame([
        _row("2026-10-20 13:30", 341.27, "yahoo_http", volume=100.0),
        _row("2026-10-20 20:00", 341.30, "yahoo_http", volume=100.1),
    ])
    out, report = canonicalize_daily_sessions(frame)
    assert len(out) == 1, "one trading day must yield exactly one bar"
    assert report["duplicate_session_rows_dropped"] == 1
    # The open-stamped row wins, so the series keeps a uniform convention.
    assert out.iloc[0]["timestamp"] == pd.Timestamp("2026-10-20 13:30", tz="UTC")
    assert out.iloc[0]["close"] == 341.27


def test_intraday_ticks_are_aggregated_into_one_daily_bar():
    frame = pd.DataFrame([
        _row("2026-10-23 08:00", 10.0, "vn_rest", volume=5.0),
        _row("2026-10-23 08:01", 10.5, "vn_rest", volume=6.0),
        _row("2026-10-23 08:02", 9.8, "vn_rest", volume=4.0),
    ])
    out, report = canonicalize_daily_sessions(frame)
    assert len(out) == 1
    assert report["intraday_days_aggregated"] == 1
    assert report["intraday_rows_aggregated"] == 3
    bar = out.iloc[0]
    assert bar["open"] == 10.0      # first tick
    assert bar["high"] == 11.5      # max (helper derives high = close + 1)
    assert bar["low"] == 8.8        # min (helper derives low = close - 1)
    assert bar["close"] == 9.8      # last tick
    assert bar["volume"] == 15.0    # summed


def test_session_bar_wins_over_intraday_rows_of_the_same_day():
    frame = pd.DataFrame([
        _row("2026-10-23 13:30", 100.0, "yahoo_http", volume=1000.0),
        _row("2026-10-23 08:00", 95.0, "manual", volume=1.0),
        _row("2026-10-23 08:01", 96.0, "manual", volume=1.0),
    ])
    out, report = canonicalize_daily_sessions(frame)
    assert len(out) == 1
    assert out.iloc[0]["close"] == 100.0
    assert report["intraday_days_aggregated"] == 0
    assert report["duplicate_session_rows_dropped"] == 2


def test_distinct_days_are_all_kept():
    frame = pd.DataFrame([
        _row("2026-10-19 13:30", 100.0, "yahoo_http"),
        _row("2026-10-20 13:30", 101.0, "yahoo_http"),
        _row("2026-10-21 13:30", 102.0, "yahoo_http"),
    ])
    out, _ = canonicalize_daily_sessions(frame)
    assert len(out) == 3
    assert list(out["timestamp"].dt.date) == [
        pd.Timestamp("2026-10-19").date(),
        pd.Timestamp("2026-10-20").date(),
        pd.Timestamp("2026-10-21").date(),
    ]


def test_dst_transition_keeps_both_stamps():
    """EDT (13:30) and EST (14:30) stamps are both legitimate."""
    frame = pd.DataFrame([
        _row("2026-07-15 13:30", 100.0, "yahoo_http"),   # EDT
        _row("2026-11-16 14:30", 101.0, "yahoo_http"),   # EST
    ])
    out, _ = canonicalize_daily_sessions(frame)
    assert len(out) == 2
    assert out.iloc[0]["timestamp"].hour == 13
    assert out.iloc[1]["timestamp"].hour == 14


def test_empty_frame_is_safe():
    frame = pd.DataFrame(columns=[
        "symbol", "timestamp", "open", "high", "low", "close", "volume", "source",
    ])
    out, report = canonicalize_daily_sessions(frame)
    assert out.empty
    assert report["rows_out"] == 0


def test_output_is_sorted_by_timestamp():
    frame = pd.DataFrame([
        _row("2026-10-21 13:30", 102.0, "yahoo_http"),
        _row("2026-10-19 13:30", 100.0, "yahoo_http"),
        _row("2026-10-20 13:30", 101.0, "yahoo_http"),
    ])
    out, _ = canonicalize_daily_sessions(frame)
    assert out["timestamp"].is_monotonic_increasing


def test_original_column_order_is_preserved():
    frame = pd.DataFrame([
        _row("2026-10-20 13:30", 100.0, "yahoo_http"),
        _row("2026-10-20 20:00", 100.1, "yahoo_http"),
    ])
    out, _ = canonicalize_daily_sessions(frame)
    assert list(out.columns) == list(frame.columns)


def test_aggregated_bar_keeps_its_own_year_and_month():
    """Regression: the aggregated bar must not inherit the frame's first month.

    A frame whose first row is in January and whose intraday day is in
    December used to have that day re-stamped into January, which then
    collided with the real January bar and produced a day with two rows.
    """
    frame = pd.DataFrame([
        _row("2024-01-05 02:00", 90000.0, "yahoo_http"),
        _row("2024-12-14 02:15", 56000.0, "vn_rest"),
        _row("2024-12-14 02:16", 56500.0, "vn_rest"),
    ])
    out, _ = canonicalize_daily_sessions(frame)
    days = list(out["timestamp"].dt.date)
    assert len(out) == len(set(days)), f"days must be unique, got {days}"
    assert pd.Timestamp("2024-12-14").date() in days


def test_intraday_aggregate_uses_first_and_last_tick_not_frame_order():
    frame = pd.DataFrame([
        _row("2026-10-23 08:02", 9.8, "vn_rest"),
        _row("2026-10-23 08:00", 10.0, "vn_rest"),
        _row("2026-10-23 08:01", 10.5, "vn_rest"),
    ])
    out, _ = canonicalize_daily_sessions(frame)
    bar = out.iloc[0]
    assert bar["open"] == 10.0   # earliest tick, not the first row
    assert bar["close"] == 9.8   # latest tick
