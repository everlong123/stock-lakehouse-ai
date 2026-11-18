"""The forecast must say how fresh its input data was.

WHY THIS TEST EXISTS
--------------------
The target-session rule targets the first trading session that is not
earlier than today and not earlier than the session after the newest
bar in Gold. When the ingestion is current, those two coincide and the
forecast is a plain next-session forecast. When the ingestion falls
behind - a failed fetch, a container restart, a holiday on the local
machine - the two separate, and the forecast silently targets a
session further away.

    10|"Silently" is the problem. The number on the row is not wrong: it is still a
forward forecast, published before the target session happened, and it
will still be scored against the real close. But a reader cannot tell
that it was made on data three sessions old, and an accuracy report
cannot separate "the model was right" from "the model was looking at
yesterday's news and predicting three days out".

So the lag is measured and carried on the forecast, and this test pins
the measurement down.

THE COUNTING RULE
------------------
The lag is counted in TRADING SESSIONS, not in calendar days. A
Friday-to-Monday gap is one session, not three days, because the
exchange was closed. The target session itself is NOT counted: it is
the session being predicted, not one that was missed. So a current
symbol - whose newest bar is the session immediately before the target
- has a lag of 0.

HOW IT RUNS
-----------
The test builds its own Gold frame from real price history where it can
read it, and falls back to a constructed calendar when the lakehouse is
unreachable. It never writes to the lakehouse and never writes to MySQL.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.forecasting import light_forecast  # noqa: E402


def _frame_from_sessions(sessions: list[date]) -> pd.DataFrame:
    """A Gold-shaped frame whose bars sit on the given trading sessions."""
    stamps = [
        pd.Timestamp(
            year=day.year,
            month=day.month,
            day=day.day,
            hour=14,
            minute=30,
            tz="UTC",
        )
        for day in sessions
    ]
    return pd.DataFrame(
        {
            "timestamp": stamps,
            "close": [100.0 + index for index in range(len(stamps))],
        }
    )


def _weekdays(count: int, end: date) -> list[date]:
    """The `count` weekdays ending on `end`, oldest first."""
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(days))


class TestStalenessCounting:
    """The lag is counted in trading sessions between the bar and the target."""

    def test_current_data_has_no_staleness(self) -> None:
        """The newest bar is the session right before the target: lag 0."""
        sessions = _weekdays(200, date(2026, 6, 30))
        frame = _frame_from_sessions(sessions)
        target = sessions[-1] + timedelta(days=1)

        assert light_forecast.staleness_days(frame, target) == 0

    def test_one_missing_session_is_counted(self) -> None:
        """A target two sessions after the newest bar: lag 1."""
        sessions = _weekdays(200, date(2026, 6, 30))
        frame = _frame_from_sessions(sessions)
        target = sessions[-1] + timedelta(days=2)

        assert light_forecast.staleness_days(frame, target) == 1

    def test_weekend_gap_is_one_session_not_three_days(self) -> None:
        """Friday to Monday is one session, because the exchange was closed."""
        # 2026-06-26 is a Friday; 2026-06-29 is the next Monday.
        sessions = _weekdays(200, date(2026, 6, 26))
        frame = _frame_from_sessions(sessions)

        assert light_forecast.staleness_days(frame, date(2026, 6, 29)) == 0

    def test_three_missing_sessions_are_counted(self) -> None:
        """A target far ahead of the newest bar: the gap is counted.

        From Tuesday 30/06 to Wednesday 08/07 there are five sessions in
        between - 01/07, 02/07, 03/07, 06/07 and 07/07 - and the target
        itself is not counted.
        """
        sessions = _weekdays(200, date(2026, 6, 30))
        frame = _frame_from_sessions(sessions)
        target = sessions[-1] + timedelta(days=8)

        assert light_forecast.staleness_days(frame, target) == 5

    def test_target_not_ahead_of_data_is_not_measured(self) -> None:
        """A target inside the frame is not a forward forecast: None."""
        sessions = _weekdays(200, date(2026, 6, 30))
        frame = _frame_from_sessions(sessions)

        assert light_forecast.staleness_days(frame, sessions[-1]) is None

    def test_empty_frame_is_not_measured(self) -> None:
        """No data means no measurement, not zero."""
        frame = pd.DataFrame({"timestamp": [], "close": []})

        assert light_forecast.staleness_days(frame, date(2026, 6, 30)) is None

    def test_missing_target_is_not_measured(self) -> None:
        """No target means no measurement, not zero."""
        sessions = _weekdays(200, date(2026, 6, 30))
        frame = _frame_from_sessions(sessions)

        assert light_forecast.staleness_days(frame, None) is None


class TestStalenessOnRealData:
    """On real Gold data, a current symbol must report a lag of 0."""

    def test_current_symbol_reports_zero(self) -> None:
        from app.lakehouse.gold import GoldLayer

        try:
            frame = GoldLayer().read("AAPL")
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"The lakehouse is not reachable: {exc}")

        if frame is None or frame.empty:
            pytest.skip("AAPL has no Gold data.")

        frame = frame.sort_values("timestamp")
        stamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True).dropna()
        latest = stamps.max()

        from app.forecasting.sessions import build_calendar

        calendar = build_calendar(frame)
        following = calendar.next_sessions(latest.date(), 1, floor=None)
        if not following:
            pytest.skip("The calendar could not place a following session.")

        lag = light_forecast.staleness_days(frame, following[0])

        # The newest bar is the session before the target, so no session
        # was missed. A non-zero value here would mean the counting rule
        # is off by one.
        assert lag == 0
