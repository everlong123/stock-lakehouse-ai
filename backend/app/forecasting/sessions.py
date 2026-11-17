"""The trading calendar of a symbol, derived from its own history.

WHY THIS FILE EXISTS
--------------------
A forecast has to name the session it is about. Getting that date wrong
does not throw an error - it produces a row that can never be verified.

The bug this module exists to fix
    10|
On 13/11/2026 the nightly batch published 151 forecasts whose target
session was Saturday 2026-11-14. No exchange trades on a Saturday, so
Gold will never hold a bar for that date, so those 151 rows would sit in
the ledger forever, unscored, and every accuracy number computed over the
ledger would be computed over a set that silently includes rows that can
never be resolved.

Why the wrong date was produced
    15|
The forward projection placed the future sessions with a CALENDAR step:
`current_ts + step`, where `step` came from `pd.infer_freq` on the
history. For a series whose spacing is irregular - which every real
equity series is, because of weekends and holidays - `infer_freq` returns
``None``, and the fallback was the median spacing, one calendar day. One
calendar day after Friday is Saturday.

WHY THE CALENDAR IS DERIVED, NOT HARD-CODED
-------------------------------------------
    20|
The obvious fix is a table of holidays. That table would be wrong for
every market in the universe that is not the US - the project holds US,
Vietnamese, Hong Kong, Korean, Japanese, Australian and European listings
- and it would need to be maintained by hand every year.

So the calendar is read off the symbol's OWN history instead:

* the WEEKDAYS on which the symbol trades are the weekdays its history
  contains bars for;
* the HOLIDAYS are the recurring absences in that history. A date that is
  missing in several different years is a holiday, not a data gap;
* a rule that recurs - "the third Monday of January" - is recognised as
  such, so a movable holiday is not mistaken for a coincidence;
* a holiday that lands on a WEEKEND is closed on another day, and WHICH
  day is a fact about the exchange, so it is learned too.

Every one of those facts comes from the lakehouse. Nothing is invented,
and the same routine works for a Vietnamese listing exactly as it does
for a US one, because it never assumes which calendar it is looking at.

THE ASYMMETRY THAT DRIVES EVERY THRESHOLD HERE
----------------------------------------------
    30|
Skipping a day the exchange DOES trade produces a forecast for the wrong
session, which then gets scored against the wrong close - a WRONG number
in the ledger, and much worse than an unscored row.

Skipping a day the exchange does NOT trade produces an unscored row: a
miss, visible and harmless.

So the algorithm is deliberately asymmetric: it skips a day only when the
history says so REPEATEDLY and CONSISTENTLY, and it never skips a day
on a single occurrence. A missed holiday costs one unscored row; a
wrongly skipped session costs a false score.

    40|THE HONEST LIMIT OF THIS APPROACH
------------------------------------
A holiday whose date moves every year - a lunar-calendar holiday, which
several Asian exchanges have - cannot be captured by any rule, because
the rule has no constant in it. Those forecasts target a day the market
is closed, and they stay unscored. That is the residual error, and it is
accepted deliberately: it is smaller than the damage a wrong skip would
do.

THE TARGET MUST ALSO BE IN THE FUTURE
--------------------------------------
    50|
A stale symbol - one whose newest bar is several sessions old - would
otherwise be given a target session that has already passed. That row
could never be scored either, and it would look like a prediction for a
session in the past. So the first target is the first session that is
both after the last known session AND not in the past.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

import pandas as pd

#: A year is only used to RECOGNISE a pattern when it holds enough
#: sessions to be a real year of trading. The first year of a symbol's
#: history is usually partial - the ingestion started in the middle of
#: it - and a partial year would make every date before the ingestion
#: started look like an absence.
MIN_SESSIONS_PER_FULL_YEAR = 150

#: How many distinct years a holiday must show up in before it is
#: accepted. One occurrence could be a data gap.
MIN_YEARS_FOR_HOLIDAY = 3

#: The share of the applicable years a holiday must cover. A holiday
#: that closes the exchange every year it applies to has a share of 1.0.
#:
#: This threshold is deliberately high. A holiday whose date drifts -
#: a lunar-calendar holiday, or a "day after the holiday" that only
#: exists in some years - lands on the same (month, day) in only some
#: years, so a loose threshold would accept it and then skip real
#: sessions in the years where it does not apply.
MIN_SHARE_FOR_HOLIDAY = 0.8

#: How many of the most recent usable years a holiday is judged over.
#:
#: The window is what makes a holiday that was INTRODUCED LATE work.
#: The Japanese holiday "Respect for the Aged Day" moved to the third
#: Monday of September in 2019, so over the whole history it only covers
#: 78% of the years - and a rule judged on the whole history would be
#: rejected, leaving the calendar blind to a holiday the exchange is
#: closed on every single year.
#:
#: The most recent years are also the ones that MATTER: a forecast
#: targets a session in the near future, so it is the CURRENT
#: convention that has to be right, not the convention of five years
#: ago. A holiday that was abolished is caught by the same window - it
#: stops being closed in the recent years, so its share collapses.
RECENT_YEARS_WINDOW = 6

#: How many times a weekend observance has to be seen before it is
#: treated as the exchange's convention rather than a coincidence.
MIN_OCCURRENCES_FOR_SHIFT = 2

#: How far ahead the search for the next session may walk. A session
#: calendar always has a session within a few days, so this is a guard
#: against an infinite loop rather than a real limit.
MAX_SEARCH_DAYS = 45

#: The marker used for a holiday defined as the LAST weekday occurrence
#: of a month - "the last Monday of May".
LAST_OCCURRENCE = -1


def _as_date(value: Any) -> date | None:
    """The calendar day of a timestamp."""
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.date()


def _occurrence_index(day: date) -> int:
    """Which occurrence of its weekday within its month this day is."""
    return (day.day - 1) // 7 + 1


def _is_last_occurrence(day: date) -> bool:
    """True when `day` is the last such weekday of its month."""
    following = day + timedelta(days=7)
    return following.month != day.month


def _nth_weekday(year: int, month: int, weekday: int, index: int) -> date | None:
    """The n-th ``weekday`` (0 = Monday) of a month; -1 means the last."""
    if index == LAST_OCCURRENCE:
        if month == 12:
            cursor = date(year, 12, 31)
        else:
            cursor = date(year, month + 1, 1)
        while True:
            cursor = cursor - timedelta(days=1)
            if cursor.month != month:
                break
        while cursor.weekday() != weekday:
            cursor = cursor - timedelta(days=1)
        return cursor

    if index < 1 or index > 5:
        return None
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    try:
        candidate = date(year, month, 1 + offset + (index - 1) * 7)
    except ValueError:
        return None
    return candidate if candidate.month == month else None


def _candidate_rules(day: date) -> list[tuple[int, int, int]]:
    """The movable rules an absence on `day` could be evidence for.

    A date can match two rules at once: "the 4th Monday of May" and
    "the last Monday of May". Both are recorded, and the conflict is
    resolved by the acceptance test - the rule that the exchange
    actually observed wins, because a holiday defined as "the last
    Monday" shifts its index between years while one defined as "the 4th
    Monday" does not, so only one of them can hold in every year.
    """
    rules = [(day.month, day.weekday(), _occurrence_index(day))]
    if _is_last_occurrence(day):
        rules.append((day.month, day.weekday(), LAST_OCCURRENCE))
    return rules


@dataclass(frozen=True)
class TradingCalendar:
    """When a symbol trades, read off its own history."""

    #: The weekdays (0 = Monday) the symbol trades on.
    weekdays: frozenset[int]
    #: Fixed-date holidays, as (month, day).
    fixed_holidays: frozenset[tuple[int, int]]
    #: Movable holidays, as (month, weekday, n-th occurrence). The index
    #: is ``LAST_OCCURRENCE`` for a holiday defined as the LAST such
    #: weekday of its month - "the last Monday of May".
    weekday_holidays: frozenset[tuple[int, int, int]]
    #: For a holiday that lands on a weekend, the day the exchange was
    #: observed to close, as an offset in days from the holiday itself.
    #: The key is the holiday; the value maps the WEEKEND WEEKDAY the
    #: holiday landed on to the offset of the closure. So
    #: ``{(7, 4): {5: -1, 6: 1}}`` means "a 4th of July that falls on a
    #: Saturday is closed on the Friday before, and one that falls on a
    #: Sunday is closed on the Monday after".
    holiday_shifts: dict[tuple[int, int], dict[int, int]] = field(default_factory=dict)
    #: The (month, day) pairs on which the exchange closes a day that
    #: sits directly between two closed days - the "substitute holiday"
    #: rule that the Japanese exchanges apply. It is learned from the
    #: history: only a symbol whose own bars prove it gets these pairs.
    sandwich_holidays: frozenset[tuple[int, int]] = frozenset()
    #: Every session the history contains, ascending.
    sessions: tuple[date, ...] = ()

    # ------------------------------------------------------------------ build

    @classmethod
    def from_history(cls, timestamps: Iterable[Any]) -> "TradingCalendar":
        """Build the calendar from the timestamps of a symbol's history."""
        days = sorted({day for day in (_as_date(value) for value in timestamps) if day})
        if not days:
            return cls(frozenset(), frozenset(), frozenset(), {}, ())

        observed = set(days)
        weekdays = {day.weekday() for day in days}

        # The years that hold enough sessions to be a real year of trading.
        per_year: dict[int, int] = {}
        for day in days:
            per_year[day.year] = per_year.get(day.year, 0) + 1
        usable_years = {
            year for year, count in per_year.items() if count >= MIN_SESSIONS_PER_FULL_YEAR
        }

        # The absences: a trading weekday with no bar, on or before the
        # last observed session. Dates AFTER the last session are not
        # absences - they are simply days that have not happened yet,
        # and counting them would teach the calendar that the whole
        # future is a holiday.
        last_observed = days[-1]
        absences = {
            day
            for day in _weekdays_of(usable_years, weekdays)
            if day <= last_observed and day not in observed
        }

        fixed, fixed_shifts = cls._fixed_holidays(
            usable_years, weekdays, absences, last_observed
        )
        movable = cls._movable_holidays(usable_years, weekdays, absences, last_observed)
        sandwiched = cls._sandwich_holidays(
            usable_years,
            weekdays,
            absences,
            fixed,
            fixed_shifts,
            movable,
            last_observed,
        )
        return cls(
            weekdays=frozenset(weekdays),
            fixed_holidays=frozenset(fixed),
            weekday_holidays=frozenset(movable),
            holiday_shifts=fixed_shifts,
            sandwich_holidays=frozenset(sandwiched),
            sessions=tuple(days),
        )

    @classmethod
    def _sandwich_holidays(
        cls,
        usable_years: set[int],
        weekdays: set[int],
        absences: set[date],
        fixed: set[tuple[int, int]],
        shifts: dict[tuple[int, int], dict[int, int]],
        movable: set[tuple[int, int, int]],
        last_observed: date,
    ) -> set[tuple[int, int]]:
        """The (month, day) pairs on which the exchange closes a squeezed day.

        Some exchanges - the Japanese ones among them - close on a
        trading day that falls directly between two closed days. It is a
        substitute-holiday rule: a holiday next to a weekend must not
        leave a lone trading day between two closures. On 22 September
        2026 the Japanese exchanges were closed between the third
        Monday and the 23rd of September, and on 22 September 2020 they
        were closed for the same reason.

        The rule is learned, not assumed, and it is learned PER (month,
        day) rather than as a single flag for the whole exchange. That
        distinction matters: the Korean exchange has days that look
        exactly like the Japanese substitute-holiday case, but it did
        NOT close on them, so a whole-exchange flag would have taken the
        Korean sessions with it. A per-pair rule keeps each exchange
        honest.

        The evidence for a pair is the days on which that pair was
        squeezed: the rule is accepted when the exchange was closed on
        EVERY one of them.

        "Every one" is the point. The Korean exchange has squeezed days
        that look exactly like the Japanese substitute-holiday case, but
        it did not close on them, so the Korean pair is rejected while
        the Japanese one is accepted. A share threshold would blur the
        two; requiring all of them keeps each exchange honest.
        """
        if not (fixed or movable) or not usable_years:
            return set()

        years = sorted(usable_years)
        # The candidates, grouped by the (month, day) they fall on.
        candidates: dict[tuple[int, int], list[date]] = {}

        for year in years:
            closed = cls._closed_days_of_year(year, weekdays, fixed, shifts, movable)
            if not closed:
                continue
            for day in _weekdays_of({year}, weekdays):
                if day in closed or day > last_observed:
                    continue
                if (day - timedelta(days=1)) in closed and (day + timedelta(days=1)) in closed:
                    candidates.setdefault((day.month, day.day), []).append(day)

        accepted: set[tuple[int, int]] = set()
        for pair, days in candidates.items():
            if all(day in absences for day in days):
                accepted.add(pair)

        return accepted

    @staticmethod
    def _closed_days_of_year(
        year: int,
        weekdays: set[int],
        fixed: set[tuple[int, int]],
        shifts: dict[tuple[int, int], dict[int, int]],
        movable: set[tuple[int, int, int]],
    ) -> set[date]:
        """Every day the calendar says is closed, in one year."""
        closed: set[date] = set()

        for month, day_number in fixed:
            try:
                holiday = date(year, month, day_number)
            except ValueError:
                continue
            closed.add(holiday)
            for weekend_weekday, offset in shifts.get((month, day_number), {}).items():
                if holiday.weekday() == weekend_weekday:
                    closed.add(holiday + timedelta(days=offset))

        for month, weekday, index in movable:
            holiday = _nth_weekday(year, month, weekday, index)
            if holiday is not None:
                closed.add(holiday)

        return closed

    # ------------------------------------------------------------- detection

    @classmethod
    def _weekend_offsets(
        cls,
        holiday: date,
        weekdays: set[int],
        absences: set[date],
        last_observed: date,
    ) -> list[int]:
        """The offsets on which a weekend holiday was observed closed.

        A holiday that lands on a weekend is closed on an adjacent day:
        the US exchanges close on the Friday before a Saturday holiday
        and on the Monday after a Sunday one, but that is a fact about
        the exchange, so the offsets are read off the history and
        returned rather than assumed.

        Only the candidate that is the IMMEDIATE adjacent day is
        considered. The convention is "the Friday before" or "the Monday
        after" - one day away - and looking further out would let a
        neighbouring date claim the same absence and be accepted as a
        holiday of its own.

        Only the candidates that are trading weekdays AND that the
        history can speak about - on or before the last observed
        session - are considered.
        """
        offsets: list[int] = []
        for offset in (-1, 1):
            candidate = holiday + timedelta(days=offset)
            if candidate.weekday() not in weekdays:
                continue
            if candidate > last_observed:
                continue
            if candidate in absences:
                offsets.append(offset)
        return offsets

    @classmethod
    def _fixed_holidays(
        cls,
        usable_years: set[int],
        weekdays: set[int],
        absences: set[date],
        last_observed: date,
    ) -> tuple[set[tuple[int, int]], dict[tuple[int, int], dict[int, int]]]:
        """Find the fixed-date holidays in the history.

        Every (month, day) of the calendar is tested. Two things are
        measured separately, because a fixed date is closed in two
        different ways:

        * when the date falls on a TRADING WEEKDAY, the exchange must
          be closed on the date itself;
        * when the date falls on a WEEKEND, the exchange is closed on an
          adjacent trading day instead, and WHICH day is recorded as
          the shift.

        The two are measured over their own years - a Saturday
        Christmas is not evidence that Christmas is a weekday closure -
        and the date is accepted as a holiday when either way of
        closing covers most of its applicable years.
        """
        if not usable_years:
            return set(), {}

        years = sorted(usable_years)
        recent = set(years[-RECENT_YEARS_WINDOW:])
        holidays: set[tuple[int, int]] = set()
        shifts: dict[tuple[int, int], dict[int, int]] = {}

        for month in range(1, 13):
            for day_number in range(1, 32):
                weekday_applicable = 0
                weekday_closed = 0
                weekday_recent_applicable = 0
                weekday_recent_closed = 0
                weekend_applicable = 0
                weekend_closed = 0
                weekend_recent_applicable = 0
                weekend_recent_closed = 0
                observed_shifts: dict[int, list[int]] = {}

                for year in years:
                    try:
                        holiday = date(year, month, day_number)
                    except ValueError:
                        continue
                    is_recent = year in recent

                    if holiday.weekday() in weekdays:
                        # The exchange must be closed on the date itself.
                        if holiday > last_observed:
                            continue
                        weekday_applicable += 1
                        if holiday in absences:
                            weekday_closed += 1
                        if is_recent:
                            weekday_recent_applicable += 1
                            if holiday in absences:
                                weekday_recent_closed += 1
                        continue

                    # The date falls on a weekend. The closure - if any -
                    # is on an adjacent trading day.
                    if holiday > last_observed:
                        continue
                    weekend_applicable += 1
                    offsets = cls._weekend_offsets(holiday, weekdays, absences, last_observed)
                    if offsets:
                        weekend_closed += 1
                        if is_recent:
                            weekend_recent_applicable += 1
                            weekend_recent_closed += 1
                        observed_shifts.setdefault(holiday.weekday(), []).extend(offsets)

                # The date is a holiday when the exchange was closed for
                # it in most of the RECENT years. The recent years are
                # the ones that decide, because a forecast targets a
                # session in the near future, and because a holiday
                # that was introduced late - or abolished late - only
                # shows up in them.
                weekday_ok = (
                    weekday_recent_applicable >= MIN_YEARS_FOR_HOLIDAY
                    and weekday_recent_closed / weekday_recent_applicable >= MIN_SHARE_FOR_HOLIDAY
                )
                weekend_ok = (
                    weekend_recent_applicable >= MIN_YEARS_FOR_HOLIDAY
                    and weekend_closed / weekend_applicable >= MIN_SHARE_FOR_HOLIDAY
                )
                if not (weekday_ok or weekend_ok):
                    continue

                holidays.add((month, day_number))

                # The shift is only recorded when the same convention
                # has been seen more than once; a single occurrence is a
                # coincidence and must not become a rule.
                recorded: dict[int, int] = {}
                for weekend_weekday, offsets in observed_shifts.items():
                    if len(offsets) < MIN_OCCURRENCES_FOR_SHIFT:
                        continue
                    recorded[weekend_weekday] = _modal(offsets)
                if recorded:
                    shifts[(month, day_number)] = recorded

        return holidays, shifts

    @classmethod
    def _movable_holidays(
        cls,
        usable_years: set[int],
        weekdays: set[int],
        absences: set[date],
        last_observed: date,
    ) -> set[tuple[int, int, int]]:
        """Find the movable holidays in the history.

        A movable holiday is a rule of the form "the n-th weekday of a
        month". The rules are proposed by the absences themselves, and
        each one is then tested the same way a fixed date is: the
        exchange's closure for the rule's date is looked up in every
        usable year, and the rule is accepted only when the exchange was
        closed for it in most of them.

        A movable holiday always lands on a weekday, so it never needs a
        shift - that only applies to fixed-date holidays that fall on a
        weekend.
        """
        if not usable_years:
            return set()

        # The rules the absences propose.
        proposed: set[tuple[int, int, int]] = set()
        for day in absences:
            proposed.update(_candidate_rules(day))

        years = sorted(usable_years)
        recent = set(years[-RECENT_YEARS_WINDOW:])
        holidays: set[tuple[int, int, int]] = set()

        for rule in proposed:
            month, weekday, index = rule
            closed_years = 0
            usable = 0
            recent_closed = 0
            recent_usable = 0

            for year in years:
                holiday = _nth_weekday(year, month, weekday, index)
                if holiday is None:
                    continue
                if holiday > last_observed:
                    continue
                usable += 1
                closed = holiday in absences
                if closed:
                    closed_years += 1
                if year in recent:
                    recent_usable += 1
                    if closed:
                        recent_closed += 1

            if usable == 0 or closed_years < MIN_YEARS_FOR_HOLIDAY:
                continue
            if recent_usable < MIN_YEARS_FOR_HOLIDAY:
                continue
            if recent_closed / recent_usable < MIN_SHARE_FOR_HOLIDAY:
                continue

            holidays.add(rule)

        return holidays

    # --------------------------------------------------------------- queries

    @property
    def weekend_shifts(self) -> dict[tuple[int, int], int]:
        """The observance of each weekend holiday, as one offset per holiday.

        ``holiday_shifts`` keeps the convention for every weekend weekday
        separately, because a Saturday holiday and a Sunday holiday can
        be closed on different days. This view collapses each holiday to
        the convention it was most often observed with, for the cases
        where one offset covers the holiday.
        """
        out: dict[tuple[int, int], int] = {}
        for holiday, by_weekday in self.holiday_shifts.items():
            offsets = [offset for _weekday, offset in by_weekday.items()]
            if offsets:
                out[holiday] = _modal(offsets)
        return out

    def is_session(self, day: date) -> bool:
        """True when the symbol trades on `day`."""
        if day.weekday() not in self.weekdays:
            return False
        if (day.month, day.day) in self.fixed_holidays:
            return False
        index = _occurrence_index(day)
        if (day.month, day.weekday(), index) in self.weekday_holidays:
            return False
        if (
            _is_last_occurrence(day)
            and (day.month, day.weekday(), LAST_OCCURRENCE) in self.weekday_holidays
        ):
            return False
        # A holiday observed on an adjacent day: the exchange closed
        # then, so that day is not a session either.
        if self.observed_holiday(day) is not None:
            return False
        # A day squeezed between two holidays: several exchanges call it
        # a substitute holiday and close as well.
        if self.is_sandwiched(day):
            return False
        return True

    def is_sandwiched(self, day: date) -> bool:
        """True when `day` sits directly between two closed days.

        The Japanese exchanges close on such a day - it is the
        "substitute holiday" rule, and it exists because a holiday
        falling next to a weekend is not allowed to leave a bare
        trading day between two closures.

        The rule is derived rather than assumed, and it is per
        (month, day): only the pairs the history proves are closed this
        way are treated that way.
        """
        if (day.month, day.day) not in self.sandwich_holidays:
            return False
        if day.weekday() not in self.weekdays:
            return False
        closed = self.closed_dates(day.year)
        return (day - timedelta(days=1)) in closed and (day + timedelta(days=1)) in closed

    def closed_dates(self, year: int) -> set[date]:
        """Every day the exchange is closed in a year.

        The set covers the fixed holidays, the movable ones, and the
        weekdays on which a weekend holiday was observed.
        """
        closed: set[date] = set()

        for month, day_number in self.fixed_holidays:
            try:
                holiday = date(year, month, day_number)
            except ValueError:
                continue
            closed.add(holiday)
            for weekend_weekday, offset in self.holiday_shifts.get(
                (month, day_number), {}
            ).items():
                if holiday.weekday() == weekend_weekday:
                    closed.add(holiday + timedelta(days=offset))

        for month, weekday, index in self.weekday_holidays:
            holiday = _nth_weekday(year, month, weekday, index)
            if holiday is not None:
                closed.add(holiday)

        return closed

    def observed_holiday(self, day: date) -> date | None:
        """The holiday `day` is the observed closure of, if any.

        A holiday that lands on a weekend is closed on a different day,
        and the exchange's convention for WHICH day was learned from the
        history. This returns the holiday date that `day` is the
        observed closure of, or None when `day` is an ordinary session.
        """
        for (month, day_number), by_weekday in self.holiday_shifts.items():
            for weekend_weekday, offset in by_weekday.items():
                holiday = day - timedelta(days=offset)
                if (
                    holiday.month == month
                    and holiday.day == day_number
                    and holiday.weekday() == weekend_weekday
                ):
                    return holiday
        return None

    def next_sessions(
        self,
        after: date,
        count: int,
        floor: date | None = None,
    ) -> list[date]:
        """The next `count` sessions after `after`.

        `floor` is the earliest session that may be returned. It is used
        to keep a stale symbol's forecast from targeting a session that
        has already passed.
        """
        if count <= 0:
            return []

        found: list[date] = []
        # The search starts at the later of the two bounds. Without this,
        # a symbol whose history stopped long before the floor would run
        # out of search days before it ever reached the floor.
        cursor = after + timedelta(days=1)
        if floor is not None and floor > cursor:
            cursor = floor
        for _ in range(MAX_SEARCH_DAYS):
            if self.is_session(cursor) and (floor is None or cursor >= floor):
                found.append(cursor)
                if len(found) >= count:
                    break
            cursor += timedelta(days=1)
        return found


def _modal(values: Sequence[int]) -> int:
    """The most common value; ties break towards the smaller offset."""
    counts: dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return max(counts.items(), key=lambda item: (item[1], -item[0]))[0]


def _weekdays_of(years: Iterable[int], weekdays: set[int]) -> set[date]:
    """Every trading weekday inside the given years."""
    out: set[date] = set()
    for year in years:
        cursor = date(year, 1, 1)
        while cursor.year == year:
            if cursor.weekday() in weekdays:
                out.add(cursor)
            cursor += timedelta(days=1)
    return out


def build_calendar(gold: pd.DataFrame) -> TradingCalendar:
    """The trading calendar of a symbol, read from its Gold frame."""
    if gold is None or gold.empty or "timestamp" not in gold.columns:
        return TradingCalendar(frozenset(), frozenset(), frozenset(), {}, ())
    return TradingCalendar.from_history(gold["timestamp"].tolist())


def future_session_timestamps(
    gold: pd.DataFrame,
    anchor: Any,
    count: int,
    floor: date | None = None,
) -> list[pd.Timestamp]:
    """The timestamps of the next `count` sessions after `anchor`.

    The time of day is copied from the anchor, because the anchor's
    timestamp carries the session's own convention (the open for a daily
    bar). Only the DATE moves, and it moves to a session the symbol
    actually trades on.
    """
    if count <= 0 or anchor is None:
        return []

    anchor_stamp = pd.Timestamp(anchor)
    if anchor_stamp.tzinfo is None:
        anchor_stamp = anchor_stamp.tz_localize("UTC")

    calendar = build_calendar(gold)
    anchor_day = anchor_stamp.date()

    if floor is None:
        floor = _today()

    days = calendar.next_sessions(anchor_day, count, floor=floor)
    return [_combine(anchor_stamp, day) for day in days]


def _today() -> date:
    """The current UTC day - the earliest session a forecast may target."""
    return datetime.now(timezone.utc).date()


def _combine(anchor: pd.Timestamp, day: date) -> pd.Timestamp:
    """The anchor's time of day on another calendar day."""
    return pd.Timestamp(
        year=day.year,
        month=day.month,
        day=day.day,
        hour=anchor.hour,
        minute=anchor.minute,
        second=anchor.second,
        tz=anchor.tz,
    )
