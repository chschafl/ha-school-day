"""Calendar entity showing school days and days off."""

from __future__ import annotations

import datetime as dt

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import SchoolDayConfigEntry, SchoolDayCoordinator, local_datetime
from .entity import SchoolDayEntity
from .model import DEFAULT_SCHEDULE, DayInfo, DayOff

PARALLEL_UPDATES = 0

# Upper bound for a single get_events request, to keep requests cheap.
MAX_QUERY_DAYS = 3 * 366


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SchoolDayConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the calendar."""
    async_add_entities([SchoolDayCalendar(entry.runtime_data)])


class SchoolDayCalendar(SchoolDayEntity, CalendarEntity):
    """School days as timed events, days off as all-day events."""

    _attr_name = None
    _attr_translation_key = "calendar"

    def __init__(self, coordinator: SchoolDayCoordinator) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator, "calendar")

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next event."""
        now = dt_util.now()
        today = now.date()
        calendar = self.coordinator.calendar
        candidates: list[CalendarEvent] = []

        info = calendar.day(today)
        if not (info.school_day and info.end and local_datetime(today, info.end) > now):
            info = calendar.next_school_day(today)
        if info is not None:
            candidates.append(self._school_event(info))

        horizon = (info.date if info else today) + dt.timedelta(days=1)
        candidates.extend(
            self._day_off_event(entry)
            for entry in calendar.days_off_between(today, horizon)
        )
        upcoming = [event for event in candidates if event.end_datetime_local > now]
        return min(upcoming, key=lambda event: event.start_datetime_local, default=None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: dt.datetime, end_date: dt.datetime
    ) -> list[CalendarEvent]:
        """Return events between start_date and end_date."""
        first = dt_util.as_local(start_date).date()
        last = min(
            dt_util.as_local(end_date).date(), first + dt.timedelta(days=MAX_QUERY_DAYS)
        )
        calendar = self.coordinator.calendar
        events = [
            self._day_off_event(entry)
            for entry in calendar.days_off_between(first, last)
        ]
        events.extend(
            self._school_event(info)
            for info in calendar.iter_days(first, last)
            if info.school_day
        )
        events = [
            event
            for event in events
            if event.end_datetime_local > start_date
            and event.start_datetime_local < end_date
        ]
        events.sort(key=lambda event: event.start_datetime_local)
        return events

    def _school_event(self, info: DayInfo) -> CalendarEvent:
        assert info.start is not None and info.end is not None
        title = self.coordinator.config_entry.title
        detail = info.label
        if detail is None and info.schedule not in (None, DEFAULT_SCHEDULE):
            detail = info.schedule.replace("_", " ").capitalize()
        return CalendarEvent(
            start=local_datetime(info.date, info.start),
            end=local_datetime(info.date, info.end),
            summary=f"{title} – {detail}" if detail else title,
            description=f"Schedule: {info.schedule}" if info.schedule else None,
            uid=f"{self.coordinator.config_entry.entry_id}-{info.date.isoformat()}",
        )

    def _day_off_event(self, entry: DayOff) -> CalendarEvent:
        return CalendarEvent(
            start=entry.range.first,
            end=entry.range.last + dt.timedelta(days=1),
            summary=f"No school – {entry.name}" if entry.name else "No school",
            uid=(
                f"{self.coordinator.config_entry.entry_id}-off-"
                f"{entry.range.first.isoformat()}-{entry.range.last.isoformat()}"
            ),
        )
