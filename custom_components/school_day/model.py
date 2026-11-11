"""School calendar model for the School Day integration.

Everything in this module is plain Python (standard library + voluptuous) so it
can be unit tested and used by ``scripts/check_calendar.py`` without a running
Home Assistant instance.

How a date is decided (first matching rule wins):

1. ``extra_days``   -> school (make-up days, extra Saturdays, ...)
2. ``days_off``     -> no school (holidays, breaks, teacher workdays, ...)
3. outside every ``school_year`` range -> no school (summer)
4. weekday not in ``week`` -> no school (weekend)
5. otherwise -> regular school day

Times for a school day start from the weekday's schedule in ``week`` and are then
adjusted by a matching extra day and by any matching ``special_days``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
import datetime as dt
import re
from typing import Any, TypeVar

import voluptuous as vol

CONF_CALENDAR = "calendar"
CONF_DATE = "date"
CONF_DAYS_OFF = "days_off"
CONF_END = "end"
CONF_EXTRA_DAYS = "extra_days"
CONF_FROM = "from"
CONF_ID = "id"
CONF_NAME = "name"
CONF_SCHEDULE = "schedule"
CONF_SCHEDULES = "schedules"
CONF_SCHOOL_YEAR = "school_year"
CONF_SPECIAL_DAYS = "special_days"
CONF_START = "start"
CONF_TO = "to"
CONF_WEEK = "week"

DEFAULT_SCHEDULE = "regular"

REASON_REGULAR = "regular"
REASON_SPECIAL_DAY = "special_day"
REASON_EXTRA_DAY = "extra_day"
REASON_DAY_OFF = "day_off"
REASON_WEEKEND = "weekend"
REASON_OUT_OF_SESSION = "out_of_session"

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

# Guard rails against typos such as a range spanning 20 years.
MAX_RANGE_DAYS = 400
LOOKAHEAD_DAYS = 400

_TIME_RE = re.compile(
    r"^(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?(?::(?P<second>\d{2}))?"
    r"\s*(?P<ampm>[ap]\.?\s?m\.?)?$",
    re.IGNORECASE,
)
_TIME_HELP = "use quoted 24h 'HH:MM' such as '08:15' or '15:20'"


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DateRange:
    """An inclusive range of dates."""

    first: dt.date
    last: dt.date

    def __contains__(self, value: object) -> bool:
        """Return True if the date is inside the range."""
        return isinstance(value, dt.date) and self.first <= value <= self.last

    @property
    def days(self) -> int:
        """Return the number of days in the range."""
        return (self.last - self.first).days + 1

    @property
    def is_single_day(self) -> bool:
        """Return True if the range covers exactly one day."""
        return self.first == self.last

    def overlaps(self, first: dt.date, last: dt.date) -> bool:
        """Return True if the range overlaps [first, last]."""
        return self.first <= last and first <= self.last


@dataclass(frozen=True)
class Schedule:
    """Start and end time of a school day."""

    start: dt.time
    end: dt.time


@dataclass(frozen=True)
class Period:
    """A school year or term in which school is in session."""

    range: DateRange
    name: str | None = None


@dataclass(frozen=True)
class DayOff:
    """A day or range of days without school."""

    range: DateRange
    name: str | None = None


@dataclass(frozen=True)
class DayChange:
    """A special day or extra day, optionally with different times."""

    range: DateRange
    name: str | None = None
    schedule: str | None = None
    start: dt.time | None = None
    end: dt.time | None = None


@dataclass(frozen=True)
class DayInfo:
    """Everything known about a single date."""

    date: dt.date
    school_day: bool
    reason: str
    label: str | None = None
    schedule: str | None = None
    start: dt.time | None = None
    end: dt.time | None = None


# --------------------------------------------------------------------------- #
# Value parsers (usable as voluptuous validators)
# --------------------------------------------------------------------------- #


def ensure_list(value: Any) -> list[Any]:
    """Wrap a single value in a list; treat None (an empty YAML key) as []."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_time(value: Any) -> dt.time:
    """Parse a time of day.

    Accepts ``"08:15"``, ``"8:15"``, ``"08:15:00"``, ``"3:20 PM"``, ``"3pm"`` and
    the integer YAML produces for an unquoted ``8:15`` (a YAML 1.1 base-60
    number: 8 * 60 + 15 = 495).
    """
    if isinstance(value, dt.time):
        return value.replace(tzinfo=None, microsecond=0)
    if isinstance(value, bool):
        raise vol.Invalid(f"invalid time {value!r}, {_TIME_HELP}")
    if isinstance(value, int):
        hours, minutes = divmod(value, 60)
        if value < 60 or hours > 23:
            raise vol.Invalid(f"invalid time {value!r}, {_TIME_HELP}")
        return dt.time(hours, minutes)
    if not isinstance(value, str):
        raise vol.Invalid(f"invalid time {value!r}, {_TIME_HELP}")

    match = _TIME_RE.match(value.strip())
    if match is None:
        raise vol.Invalid(f"invalid time {value!r}, {_TIME_HELP}")
    hour = int(match["hour"])
    minute = int(match["minute"] or 0)
    second = int(match["second"] or 0)
    if ampm := match["ampm"]:
        if not 1 <= hour <= 12:
            raise vol.Invalid(f"invalid time {value!r}, {_TIME_HELP}")
        hour = hour % 12 + (12 if ampm.lower().startswith("p") else 0)
    elif match["minute"] is None:
        raise vol.Invalid(f"invalid time {value!r}, {_TIME_HELP}")
    try:
        return dt.time(hour, minute, second)
    except ValueError as err:
        raise vol.Invalid(f"invalid time {value!r}, {_TIME_HELP}") from err


def parse_date(value: Any) -> dt.date:
    """Parse a date in ISO format (YYYY-MM-DD)."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise vol.Invalid(f"invalid date {value!r}, use YYYY-MM-DD such as 2026-09-02")


def parse_weekday(value: Any) -> int:
    """Parse a weekday name ("mon", "Monday", "thurs", ...) to 0 (Mon) - 6 (Sun)."""
    if isinstance(value, str):
        key = value.strip().lower()
        for index, (short, full) in enumerate(
            zip(WEEKDAYS, WEEKDAY_NAMES, strict=True)
        ):
            if key == short or (len(key) >= 3 and full.startswith(key)):
                return index
    raise vol.Invalid(
        f"invalid weekday {value!r}, use mon, tue, wed, thu, fri, sat or sun"
    )


def _expand_weekdays(value: Any) -> list[int]:
    """Parse a weekday or a range of weekdays such as "mon-fri"."""
    if isinstance(value, str) and "-" in value:
        first, last = (parse_weekday(part) for part in value.split("-", 1))
        if first > last:
            raise vol.Invalid(f"invalid weekday range {value!r}, use e.g. mon-fri")
        return list(range(first, last + 1))
    return [parse_weekday(value)]


def parse_schedule(value: Any) -> Schedule:
    """Parse ``{start: "08:00", end: "15:00"}``."""
    data = vol.Schema(
        {vol.Required(CONF_START): parse_time, vol.Required(CONF_END): parse_time}
    )(value)
    if data[CONF_START] >= data[CONF_END]:
        raise vol.Invalid(
            f"start {data[CONF_START]:%H:%M} must be before end {data[CONF_END]:%H:%M}"
        )
    return Schedule(data[CONF_START], data[CONF_END])


def parse_week(value: Any) -> dict[int, str | Schedule]:
    """Parse the regular school week.

    Accepted forms::

        week: [mon, tue, wed, thu, fri]        # every day uses "regular"
        week: mon-fri                          # same
        week:                                  # weekday -> schedule name
          mon-thu: regular
          fri: early_release
        week:                                  # or inline times
          wed: { start: "08:50", end: "13:20" }
    """
    if isinstance(value, str):
        value = [part for part in re.split(r"[,\s]+", value) if part]
    if isinstance(value, list):
        week: dict[int, str | Schedule] = {}
        for item in value:
            for day in _expand_weekdays(item):
                week[day] = DEFAULT_SCHEDULE
        return week
    if isinstance(value, dict):
        week = {}
        for key, schedule in value.items():
            days = _expand_weekdays(key)
            if schedule is False:  # "fri: off" -> no school on Fridays
                for day in days:
                    week.pop(day, None)
                continue
            if schedule is None or schedule is True:
                parsed: str | Schedule = DEFAULT_SCHEDULE
            elif isinstance(schedule, str):
                parsed = schedule.strip()
            elif isinstance(schedule, dict):
                parsed = parse_schedule(schedule)
            else:
                raise vol.Invalid(
                    f"invalid schedule for {key!r}: use a schedule name or "
                    "{start: 'HH:MM', end: 'HH:MM'}"
                )
            for day in days:
                week[day] = parsed
        return week
    raise vol.Invalid(
        "week must be a list of weekdays (e.g. [mon, tue, wed, thu, fri]) "
        "or a mapping of weekday to schedule"
    )


def _dated_entry(
    extra: dict[Any, Any],
    *,
    allow_bare_date: bool = False,
    allow_single_date: bool = True,
) -> vol.Schema:
    """Build a validator for entries that have a ``date`` or ``from``/``to``."""
    schema = vol.Schema(
        {
            vol.Optional(CONF_DATE): parse_date,
            vol.Optional(CONF_FROM): parse_date,
            vol.Optional(CONF_TO): parse_date,
            vol.Optional(CONF_NAME): vol.Any(None, vol.Coerce(str)),
            **extra,
        }
    )

    def validate(value: Any) -> dict[str, Any]:
        if allow_bare_date and not isinstance(value, dict):
            value = {CONF_DATE: value}
        data = schema(value)
        has_date = CONF_DATE in data
        has_range = CONF_FROM in data or CONF_TO in data
        if has_date and has_range:
            raise vol.Invalid("use either 'date' or 'from'/'to', not both")
        if has_date and not allow_single_date:
            raise vol.Invalid("use 'from' and 'to'")
        if has_range and not (CONF_FROM in data and CONF_TO in data):
            raise vol.Invalid("a range needs both 'from' and 'to'")
        if not has_date and not has_range:
            raise vol.Invalid("missing 'date' (or 'from' and 'to')")
        first = data.pop(CONF_DATE, None) or data.pop(CONF_FROM)
        last = data.pop(CONF_TO, None) or first
        if last < first:
            raise vol.Invalid(f"'to' ({last}) is before 'from' ({first})")
        if (last - first).days >= MAX_RANGE_DAYS:
            raise vol.Invalid(f"range {first} to {last} is longer than a year")
        data["range"] = DateRange(first, last)
        return data

    return validate


_period_entry = _dated_entry({}, allow_single_date=False)
_day_off_entry = _dated_entry({}, allow_bare_date=True)
_change_keys = {
    vol.Optional(CONF_SCHEDULE): vol.Coerce(str),
    vol.Optional(CONF_START): parse_time,
    vol.Optional(CONF_END): parse_time,
}
_extra_day_entry = _dated_entry(_change_keys, allow_bare_date=True)
_special_day_entry = _dated_entry(_change_keys)


def _to_period(value: Any) -> Period:
    data = _period_entry(value)
    return Period(data["range"], data.get(CONF_NAME))


def _to_day_off(value: Any) -> DayOff:
    data = _day_off_entry(value)
    return DayOff(data["range"], data.get(CONF_NAME))


def _to_change(data: dict[str, Any]) -> DayChange:
    return DayChange(
        data["range"],
        data.get(CONF_NAME),
        data.get(CONF_SCHEDULE),
        data.get(CONF_START),
        data.get(CONF_END),
    )


def _to_extra_day(value: Any) -> DayChange:
    return _to_change(_extra_day_entry(value))


def _to_special_day(value: Any) -> DayChange:
    data = _special_day_entry(value)
    if not any(key in data for key in (CONF_SCHEDULE, CONF_START, CONF_END)):
        raise vol.Invalid("a special day needs 'schedule', 'start' or 'end'")
    return _to_change(data)


CALENDAR_KEYS: dict[Any, Any] = {
    vol.Optional(CONF_SCHEDULES): vol.Any(None, vol.Schema({str: parse_schedule})),
    vol.Optional(CONF_WEEK): parse_week,
    vol.Optional(CONF_SCHOOL_YEAR): vol.All(ensure_list, [_to_period]),
    vol.Optional(CONF_DAYS_OFF): vol.All(ensure_list, [_to_day_off]),
    vol.Optional(CONF_SPECIAL_DAYS): vol.All(ensure_list, [_to_special_day]),
    vol.Optional(CONF_EXTRA_DAYS): vol.All(ensure_list, [_to_extra_day]),
}

# A calendar fragment holds everything except the school's identity. It is what
# ``calendar: !include district-2026-27.yaml`` points at, so several schools of
# one district can share the dates and only differ in their bell times.
CALENDAR_SCHEMA = vol.Schema(
    {vol.Optional(CONF_NAME): vol.Any(None, vol.Coerce(str)), **CALENDAR_KEYS}
)  # a fragment's own name (e.g. "District 2026-27") is only informational

SCHOOL_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): vol.Coerce(str),
        vol.Optional(CONF_ID): vol.Coerce(str),
        vol.Optional(CONF_CALENDAR): vol.All(ensure_list, [CALENDAR_SCHEMA]),
        **CALENDAR_KEYS,
    }
)


def validate_school(value: Any) -> dict[str, Any]:
    """Validate one school and merge its calendar fragments.

    Returns a flat dict that :meth:`SchoolCalendar.from_config` accepts. Lists
    (school_year, days_off, special_days, extra_days) are concatenated; the
    school's own ``schedules`` and ``week`` win over those of its calendars.
    """
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise vol.Invalid("a school must be a mapping of settings")
    data = SCHOOL_SCHEMA(value)
    merged: dict[str, Any] = {
        CONF_NAME: data.get(CONF_NAME),
        CONF_ID: data.get(CONF_ID),
        CONF_SCHEDULES: {},
        CONF_WEEK: None,
        CONF_SCHOOL_YEAR: [],
        CONF_DAYS_OFF: [],
        CONF_SPECIAL_DAYS: [],
        CONF_EXTRA_DAYS: [],
    }
    for fragment in [*data.get(CONF_CALENDAR, []), data]:
        merged[CONF_SCHEDULES].update(fragment.get(CONF_SCHEDULES) or {})
        if CONF_WEEK in fragment:
            merged[CONF_WEEK] = fragment[CONF_WEEK]
        for key in (
            CONF_SCHOOL_YEAR,
            CONF_DAYS_OFF,
            CONF_SPECIAL_DAYS,
            CONF_EXTRA_DAYS,
        ):
            merged[key].extend(fragment.get(key, []))
    SchoolCalendar.from_config(merged)  # raises vol.Invalid on semantic errors
    return merged


# --------------------------------------------------------------------------- #
# The calendar
# --------------------------------------------------------------------------- #


_EntryT = TypeVar("_EntryT", DayOff, DayChange)


def _best_match(entries: Iterable[_EntryT], date: dt.date) -> _EntryT | None:
    """Return the most specific entry covering the date (shortest range, last wins)."""
    best: _EntryT | None = None
    for entry in entries:
        if date in entry.range and (
            best is None or entry.range.days <= best.range.days
        ):
            best = entry
    return best


class SchoolCalendar:
    """Answers "is there school on this date, and when?"."""

    def __init__(
        self,
        *,
        schedules: dict[str, Schedule],
        week: dict[int, str],
        periods: list[Period],
        days_off: list[DayOff],
        special_days: list[DayChange],
        extra_days: list[DayChange],
    ) -> None:
        """Initialize the calendar from already validated parts."""
        self.schedules = schedules
        self.week = week
        self.periods = sorted(periods, key=lambda period: period.range.first)
        self.days_off = days_off
        self.special_days = special_days
        self.extra_days = extra_days

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> SchoolCalendar:
        """Build a calendar from the output of :func:`validate_school`."""
        schedules: dict[str, Schedule] = dict(config.get(CONF_SCHEDULES) or {})
        raw_week = config.get(CONF_WEEK)
        if raw_week is None:
            raw_week = dict.fromkeys(range(5), DEFAULT_SCHEDULE)

        week: dict[int, str] = {}
        for day, ref in sorted(raw_week.items()):
            if isinstance(ref, Schedule):
                key = WEEKDAY_NAMES[day]
                if key in schedules and schedules[key] != ref:
                    raise vol.Invalid(
                        f"week: inline times for {key} clash with the schedule "
                        f"named '{key}'"
                    )
                schedules[key] = ref
                ref = key
            elif ref not in schedules:
                raise vol.Invalid(
                    f"week: {WEEKDAY_NAMES[day]} uses schedule '{ref}' which is not "
                    f"defined under 'schedules' (defined: {_names(schedules)})"
                )
            week[day] = ref

        special_days = list(config.get(CONF_SPECIAL_DAYS, []))
        extra_days = list(config.get(CONF_EXTRA_DAYS, []))
        for kind, changes in (
            ("special_days", special_days),
            ("extra_days", extra_days),
        ):
            for change in changes:
                if change.schedule is not None and change.schedule not in schedules:
                    raise vol.Invalid(
                        f"{kind}: '{_describe(change)}' uses schedule "
                        f"'{change.schedule}' which is not defined under 'schedules' "
                        f"(defined: {_names(schedules)})"
                    )

        calendar = cls(
            schedules=schedules,
            week=week,
            periods=list(config.get(CONF_SCHOOL_YEAR, [])),
            days_off=list(config.get(CONF_DAYS_OFF, [])),
            special_days=special_days,
            extra_days=extra_days,
        )
        calendar._validate_changes()
        return calendar

    def _validate_changes(self) -> None:
        """Resolve every special/extra day once so bad times fail at load time."""
        for change in (*self.extra_days, *self.special_days):
            date = change.range.first
            while date <= change.range.last:
                try:
                    self.day(date)
                except ValueError as err:
                    raise vol.Invalid(str(err)) from err
                date += dt.timedelta(days=1)

    # -- single day --------------------------------------------------------- #

    def day(self, date: dt.date) -> DayInfo:
        """Return whether the date is a school day and its times."""
        weekday = date.weekday()
        extra = _best_match(
            (
                entry
                for entry in self.extra_days
                # A range never turns a weekend into a school day; use a single
                # 'date' entry for a Saturday make-up day.
                if entry.range.is_single_day or weekday in self.week
            ),
            date,
        )

        if extra is None:
            if (off := _best_match(self.days_off, date)) is not None:
                return DayInfo(date, False, REASON_DAY_OFF, off.name)
            if self.periods and not any(date in p.range for p in self.periods):
                return DayInfo(date, False, REASON_OUT_OF_SESSION)
            if weekday not in self.week:
                return DayInfo(date, False, REASON_WEEKEND)

        schedule_name = self.week.get(weekday, DEFAULT_SCHEDULE)
        reason = REASON_EXTRA_DAY if extra else REASON_REGULAR
        label = extra.name if extra else None
        changes: list[DayChange] = [extra] if extra else []

        # Wider ranges first so a single date can refine e.g. a conference week.
        specials = sorted(
            (entry for entry in self.special_days if date in entry.range),
            key=lambda entry: -entry.range.days,
        )
        if specials:
            if extra is None:
                reason = REASON_SPECIAL_DAY
            label = next(
                (entry.name for entry in reversed(specials) if entry.name), label
            )
            changes.extend(specials)

        base = self.schedules.get(schedule_name)
        start = base.start if base else None
        end = base.end if base else None
        for change in changes:
            if change.schedule is not None:
                schedule_name = change.schedule
                start = self.schedules[change.schedule].start
                end = self.schedules[change.schedule].end
            if change.start is not None:
                start = change.start
            if change.end is not None:
                end = change.end

        if start is None or end is None:
            raise ValueError(
                f"{date} ({label or reason}): no times known; define a "
                f"'{schedule_name}' schedule or give 'start' and 'end'"
            )
        if start >= end:
            raise ValueError(
                f"{date} ({label or reason}): start {start:%H:%M} is not before "
                f"end {end:%H:%M}"
            )
        return DayInfo(date, True, reason, label, schedule_name, start, end)

    # -- ranges ------------------------------------------------------------- #

    def iter_days(self, first: dt.date, last: dt.date) -> Iterator[DayInfo]:
        """Yield a DayInfo for every date in [first, last]."""
        date = first
        while date <= last:
            yield self.day(date)
            date += dt.timedelta(days=1)

    def count_school_days(self, first: dt.date, last: dt.date) -> int:
        """Count school days in [first, last]."""
        return sum(1 for info in self.iter_days(first, last) if info.school_day)

    def _last_possible_school_day(self, after: dt.date) -> dt.date:
        limit = after + dt.timedelta(days=LOOKAHEAD_DAYS)
        if not self.periods:
            return limit
        latest = max(
            [p.range.last for p in self.periods]
            + [e.range.last for e in self.extra_days]
        )
        return min(limit, latest)

    def next_school_day(self, after: dt.date) -> DayInfo | None:
        """Return the first school day strictly after the given date."""
        last = self._last_possible_school_day(after)
        for info in self.iter_days(after + dt.timedelta(days=1), last):
            if info.school_day:
                return info
        return None

    def period_for(self, date: dt.date) -> Period | None:
        """Return the school year containing the date, else the next one."""
        for period in self.periods:
            if date in period.range:
                return period
        upcoming = [p for p in self.periods if p.range.first > date]
        return upcoming[0] if upcoming else None

    def days_off_between(self, first: dt.date, last: dt.date) -> list[DayOff]:
        """Return the days_off entries overlapping [first, last]."""
        return [entry for entry in self.days_off if entry.range.overlaps(first, last)]


def _names(schedules: dict[str, Schedule]) -> str:
    return ", ".join(sorted(schedules)) or "none"


def _describe(change: DayChange) -> str:
    if change.name:
        return change.name
    if change.range.is_single_day:
        return str(change.range.first)
    return f"{change.range.first} to {change.range.last}"
