"""A forecast must never target a day the market does not trade.

WHY THIS TEST EXISTS
--------------------
The nightly batch published 151 forecasts whose target session was
Saturday 2026-11-14 (measured 13/11/2026). No exchange trades on a
Saturday, so Gold will never hold a bar for that date, so those rows sat
in the verification ledger forever, unscored - and every accuracy number
computed over the ledger was computed over a set that silently contained
rows that could never be resolved.

The cause was a CALENDAR step: the forward projection advanced the
timestamp by one calendar day, because `pd.infer_freq` returns None on a
real equity series (the spacing is irregular - weekends, holidays) and
the fallback was the median spacing.

So the target session must be derived from the symbol's OWN trading
calendar, read off its Gold history. This test pins that behaviour with
SYNTHETIC calendars - the shape of a series is what matters here, and a
synthetic series makes the expected answer obvious. The real-data check
is in `test_light_path_matches_full_path.py`, which compares the two
forecast paths against each other on the actual lakehouse.

The synthetic series here are NOT market data: they are a test fixture
for the calendar logic, and they never enter the lakehouse.
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

from app.forecasting import sessions  # noqa: E402

#: The tests below pin a specific set of dates, so the "not in the past"
#: guard must not move with the wall clock. The floor is deliberately
#: early: the point of these tests is the CALENDAR, not the staleness
#: rule, which has its own test further down.
_FLOOR = date(2020, 1, 1)


def _daily_series(days: list[date], hour: int = 14, minute: int = 30) -> pd.DataFrame:
    """A Gold-like frame whose bars fall on the given dates."""
    stamps = [
        pd.Timestamp(
            year=day.year,
            month=day.month,
            day=day.day,
            hour=hour,
            minute=minute,
            tz="UTC",
        )
        for day in days
    ]
    return pd.DataFrame({"timestamp": stamps, "close": [100.0 + i for i in range(len(stamps))]})


def _weekdays_between(start: date, end: date) -> list[date]:
    """Every Mon-Fri between two dates."""
    out: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor += timedelta(days=1)
    return out


def _with_holidays(
    days: list[date],
    holidays: list[date],
) -> list[date]:
    """The series minus its holidays."""
    blocked = set(holidays)
    return [day for day in days if day not in blocked]


class TestWeekendsAreNeverTargeted:
    """The bug: Saturday and Sunday must be skipped."""

    def test_friday_rolls_forward_to_monday(self) -> None:
        """The Friday-after-the-Friday case that produced the 151 rows."""
        history = _weekdays_between(date(2024, 1, 1), date(2026, 11, 13))
        frame = _daily_series(history)

        targets = sessions.future_session_timestamps(
            frame, pd.Timestamp("2026-11-13 14:30:00+00:00"), 1, floor=_FLOOR
        )

        assert len(targets) == 1
        assert targets[0].date() == date(2026, 11, 16), (
            "The forecast after a Friday must target the following Monday, "
            f"not {targets[0].date()}."
        )

    def test_a_multi_step_horizon_skips_every_weekend(self) -> None:
        """Each step of a horizon lands on a trading weekday."""
        history = _weekdays_between(date(2024, 1, 1), date(2026, 11, 13))
        frame = _daily_series(history)

        targets = sessions.future_session_timestamps(
            frame, pd.Timestamp("2026-11-13 14:30:00+00:00"), 5, floor=_FLOOR
        )

        assert len(targets) == 5
        for target in targets:
            assert target.weekday() < 5, f"{target.date()} is a weekend."

        # And the steps must be consecutive trading days, in order.
        assert [t.date() for t in targets] == [
            date(2026, 11, 16),
            date(2026, 11, 17),
            date(2026, 11, 18),
            date(2026, 11, 19),
            date(2026, 11, 20),
        ]

    def test_the_time_of_day_is_preserved(self) -> None:
        """Only the DATE moves; the session's own convention stays."""
        history = _weekdays_between(date(2024, 1, 1), date(2026, 11, 13))
        frame = _daily_series(history, hour=9, minute=15)

        targets = sessions.future_session_timestamps(
            frame, pd.Timestamp("2026-11-13 09:15:00+00:00"), 1, floor=_FLOOR
        )

        assert targets[0].hour == 9
        assert targets[0].minute == 15
        assert str(targets[0].tz) == "UTC"


class TestHolidaysAreSkipped:
    """A recurring absence in the history is a holiday, not a gap."""

    def test_a_fixed_date_holiday_is_skipped(self) -> None:
        """Christmas is absent every year, so it is a holiday."""
        days = _weekdays_between(date(2021, 1, 1), date(2026, 11, 13))
        holidays = [date(year, 12, 25) for year in range(2021, 2027)]
        holidays = [d for d in holidays if d.weekday() < 5]
        frame = _daily_series(_with_holidays(days, holidays))

        targets = sessions.future_session_timestamps(
            frame,
            pd.Timestamp("2026-12-24 14:30:00+00:00"),
            1,
            floor=_FLOOR,
        )

        assert targets[0].date() == date(2026, 12, 28), (
            "The forecast before Christmas must skip the holiday and the "
            "weekend, not target a day nobody trades."
        )

    def test_a_movable_holiday_is_skipped(self) -> None:
        """A holiday defined by its weekday within the month is found too.

        The 4th Monday of May is a real US holiday. The series omits it
        every year, so the calendar must learn the rule rather than just
        the dates.
        """
        days = _weekdays_between(date(2021, 1, 1), date(2026, 11, 13))
        holidays: list[date] = []
        for year in range(2021, 2027):
            cursor = date(year, 5, 1)
            mondays = []
            while cursor.month == 5:
                if cursor.weekday() == 0:
                    mondays.append(cursor)
                cursor += timedelta(days=1)
            if len(mondays) >= 4:
                holidays.append(mondays[3])
        frame = _daily_series(_with_holidays(days, holidays))

        calendar = sessions.build_calendar(frame)
        assert (5, 0, 4) in calendar.weekday_holidays, (
            "The 4th Monday of May must be recognised as a holiday."
        )

    def test_a_one_off_gap_is_not_treated_as_a_holiday(self) -> None:
        """A single missing day is a data gap, not a holiday.

        If one-off gaps were treated as holidays, the calendar would start
        skipping real sessions - which is worse than the bug it fixes,
        because the skipped session would be a real trading day.
        """
        days = _weekdays_between(date(2021, 1, 1), date(2026, 11, 13))
        # One single missing Wednesday, in one single year.
        gap = date(2024, 5, 15)
        frame = _daily_series([d for d in days if d != gap])

        calendar = sessions.build_calendar(frame)
        assert (5, 15) not in calendar.fixed_holidays
        assert calendar.is_session(date(2026, 5, 15))


class TestHolidayObservedOnAnotherDay:
    """A holiday that lands on a weekend is closed on another day.

    WHICH day is a fact about the exchange, so it is read off the
    history rather than assumed. The US exchanges close on the Friday
    before a Saturday holiday and on the Monday after a Sunday one -
    and the calendar learns exactly that from the data.
    """

    def _series_with_shifted_holiday(self) -> pd.DataFrame:
        """A series whose 4th of July is closed on the adjacent weekday.

        The closure follows the US rule: the holiday is closed on the
        4th itself when that is a weekday, on the Friday before when it
        falls on a Saturday, and on the Monday after when it falls on a
        Sunday.

        The history starts in 2010 so that both conventions are seen more
        than once - the calendar refuses to learn a rule from a single
        occurrence. The 4th of July falls on a Sunday in 2010, 2015 and
        2021, and on a Saturday in 2014, 2020 and 2026.
        """
        days = _weekdays_between(date(2010, 1, 1), date(2026, 11, 13))
        closures: list[date] = []
        for year in range(2010, 2027):
            holiday = date(year, 7, 4)
            if holiday.weekday() < 5:
                closures.append(holiday)
            elif holiday.weekday() == 5:  # Saturday -> the Friday before
                closures.append(holiday - timedelta(days=1))
            else:  # Sunday -> the Monday after
                closures.append(holiday + timedelta(days=1))
        return _daily_series(_with_holidays(days, closures))

    def test_the_convention_is_learned_from_the_history(self) -> None:
        """The calendar learns the shift instead of hard-coding it.

        The rule is stored per HOLIDAY, because it is a fact about that
        holiday on that exchange - and the exchanges differ. A single
        global rule would be wrong for one of them.
        """
        calendar = sessions.build_calendar(self._series_with_shifted_holiday())

        # The 4th of July is closed on the Friday before when it falls
        # on a Saturday, and on the Monday after when it falls on a
        # Sunday - so both observations point at the same offset.
        assert calendar.weekend_shifts.get((7, 4)) == -1

    def test_a_per_holiday_rule_beats_the_weekday_fallback(self) -> None:
        """Two holidays can be observed on DIFFERENT days.

        The US exchanges close on the Friday before a Saturday holiday,
        while the Korean exchange closes on the following Monday. When
        both holidays land on a Saturday, the two rules disagree, and
        applying the same rule to both would skip a real trading day for
        one of them.
        """
        days = _weekdays_between(date(2010, 1, 1), date(2026, 11, 13))
        closures: list[date] = []
        for year in range(2010, 2027):
            first = date(year, 7, 4)
            second = date(year, 8, 15)
            for holiday, offset in ((first, -1), (second, 1)):
                if holiday.weekday() == 5:  # Saturday
                    closures.append(holiday + timedelta(days=offset))
                elif holiday.weekday() == 6:  # Sunday
                    closures.append(holiday + timedelta(days=offset))
                else:
                    closures.append(holiday)
        frame = _daily_series(_with_holidays(days, closures))

        calendar = sessions.build_calendar(frame)
        assert calendar.weekend_shifts.get((7, 4)) == -1
        assert calendar.weekend_shifts.get((8, 15)) == 1

    def test_the_observed_closure_day_is_not_a_session(self) -> None:
        """The day the exchange actually closed is not a trading day."""
        calendar = sessions.build_calendar(self._series_with_shifted_holiday())

        # 2021-07-04 is a Sunday, so the exchange closed on Monday the 5th.
        assert not calendar.is_session(date(2021, 7, 5))
        # And the day before is an ordinary session.
        assert calendar.is_session(date(2021, 7, 6))

    def test_a_weekend_holiday_needs_more_than_one_occurrence(self) -> None:
        """One occurrence could be a coincidence, so it is not a rule.

        A calendar that learned a convention from a single occurrence
        would skip real sessions in every other year - a worse failure
        than the one it was meant to prevent.
        """
        days = _weekdays_between(date(2021, 1, 1), date(2026, 11, 13))
        # Only ONE weekend holiday in the whole history.
        closures = [date(2021, 7, 5)]
        frame = _daily_series(_with_holidays(days, closures))

        calendar = sessions.build_calendar(frame)
        assert calendar.weekend_shifts == {}


class TestTheCalendarIsNotHardCoded:
    """The calendar must follow the symbol's own history."""

    def test_a_market_that_trades_on_saturday_is_honoured(self) -> None:
        """A symbol whose history contains Saturdays trades on Saturdays.

        This is the reason the calendar is derived rather than hard-coded:
        the project holds listings from several exchanges, and a calendar
        that assumed Mon-Fri would be wrong for every one of them.
        """
        days: list[date] = []
        cursor = date(2024, 1, 1)
        while cursor <= date(2026, 11, 13):
            if cursor.weekday() != 6:  # skip Sunday only
                days.append(cursor)
            cursor += timedelta(days=1)
        frame = _daily_series(days)

        calendar = sessions.build_calendar(frame)
        # Saturday is a trading day for this symbol; Sunday is not.
        assert 5 in calendar.weekdays
        assert 6 not in calendar.weekdays
        assert calendar.is_session(date(2026, 11, 14))

        targets = sessions.future_session_timestamps(
            frame, pd.Timestamp("2026-11-13 14:30:00+00:00"), 1, floor=date(2020, 1, 1)
        )
        assert targets[0].date() == date(2026, 11, 14)


class TestStaleSymbols:
    """A stale symbol must not target a session in the past."""

    def test_a_target_in_the_past_is_pushed_forward(self) -> None:
        """The target may not be a session that has already happened."""
        history = _weekdays_between(date(2024, 1, 1), date(2025, 6, 30))
        frame = _daily_series(history)

        floor = date(2026, 11, 13)
        targets = sessions.future_session_timestamps(
            frame,
            pd.Timestamp("2025-06-30 14:30:00+00:00"),
            1,
            floor=floor,
        )

        assert targets, "A stale symbol must still get a target session."
        assert targets[0].date() >= floor


def test_the_module_never_raises_on_an_empty_history() -> None:
    """An empty frame yields no sessions, not an exception."""
    empty = pd.DataFrame({"timestamp": [], "close": []})
    calendar = sessions.build_calendar(empty)
    assert calendar.sessions == ()
    assert sessions.future_session_timestamps(empty, pd.Timestamp("2026-11-13"), 3) == []


@pytest.mark.parametrize("weekday", [0, 1, 2, 3, 4])
def test_every_weekday_rolls_forward(weekday: int) -> None:
    """From any weekday, the next target is the next trading day.

    The distance must be 1 day across a weekday boundary and 3 days over
    a weekend - never 2, which is what a Saturday target looks like.
    """
    days = _weekdays_between(date(2024, 1, 1), date(2026, 11, 13))
    frame = _daily_series(days)

    # 2026-11-09 is a Monday, so adding `weekday` lands on every weekday
    # of that week.
    anchor = date(2026, 11, 9) + timedelta(days=weekday)
    if anchor.weekday() > 4:
        pytest.skip("The anchor must be a weekday.")

    targets = sessions.future_session_timestamps(
        frame, pd.Timestamp(f"{anchor.isoformat()} 14:30:00+00:00"), 1, floor=_FLOOR
    )
    assert targets, f"No target for an anchor on {anchor}."
    gap = (targets[0].date() - anchor).days
    assert gap in (1, 3), (
        f"An anchor on {anchor} produced a target {gap} days later; "
        "a gap of 2 days means a weekend was targeted."
    )
