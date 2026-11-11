"""Keeps the School Day entities up to date."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import datetime as dt
import logging
import os
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_time_interval,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    FILE_CHECK_INTERVAL,
    STATUS_AFTER_SCHOOL,
    STATUS_BEFORE_SCHOOL,
    STATUS_IN_SCHOOL,
    STATUS_NO_SCHOOL,
)
from .loader import SchoolFileError, load_school_file
from .model import DayInfo, Period, SchoolCalendar

_LOGGER = logging.getLogger(__name__)

type SchoolDayConfigEntry = ConfigEntry[SchoolDayCoordinator]


@dataclass(frozen=True)
class SchoolDayData:
    """A snapshot of the school calendar at a point in time."""

    now: dt.datetime
    today: DayInfo
    tomorrow: DayInfo
    status: str
    start: dt.datetime | None
    end: dt.datetime | None
    next_school_day: DayInfo | None
    period: Period | None
    days_left: int | None
    days_total: int | None


def local_datetime(date: dt.date, time: dt.time) -> dt.datetime:
    """Combine a date and a wall-clock time in Home Assistant's time zone."""
    return dt.datetime.combine(date, time, tzinfo=dt_util.get_default_time_zone())


def build_snapshot(calendar: SchoolCalendar, now: dt.datetime) -> SchoolDayData:
    """Compute everything the entities show for the given moment."""
    today = now.date()
    info = calendar.day(today)
    start = end = None
    if info.school_day and info.start and info.end:
        start = local_datetime(today, info.start)
        end = local_datetime(today, info.end)
        if now < start:
            status = STATUS_BEFORE_SCHOOL
        elif now < end:
            status = STATUS_IN_SCHOOL
        else:
            status = STATUS_AFTER_SCHOOL
    else:
        status = STATUS_NO_SCHOOL

    period = calendar.period_for(today)
    days_left = days_total = None
    if period is not None:
        days_total = calendar.count_school_days(period.range.first, period.range.last)
        first = max(today, period.range.first)
        days_left = calendar.count_school_days(first, period.range.last)
        if first == today and status == STATUS_AFTER_SCHOOL:
            days_left -= 1  # today is done

    return SchoolDayData(
        now=now,
        today=info,
        tomorrow=calendar.day(today + dt.timedelta(days=1)),
        status=status,
        start=start,
        end=end,
        next_school_day=calendar.next_school_day(today),
        period=period,
        days_left=days_left,
        days_total=days_total,
    )


def next_transition(data: SchoolDayData) -> dt.datetime:
    """Return when the snapshot changes next: school start, end or midnight."""
    midnight = dt_util.start_of_local_day(data.now.date() + dt.timedelta(days=1))
    candidates = [
        moment
        for moment in (data.start, data.end)
        if moment is not None and moment > data.now
    ]
    return min([*candidates, midnight])


class SchoolDayCoordinator(DataUpdateCoordinator[SchoolDayData]):
    """Recomputes the snapshot at school start, school end and midnight."""

    config_entry: SchoolDayConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SchoolDayConfigEntry,
        calendar: SchoolCalendar,
        file_path: Path | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=None,
        )
        self.calendar = calendar
        self.file_path = file_path
        self._file_mtime: float | None = None
        self._unsub_transition: Callable[[], None] | None = None
        self._unsub_file_check: Callable[[], None] | None = None

    @property
    def issue_id(self) -> str:
        """Return the repair issue id used for an invalid calendar file."""
        return f"invalid_file_{self.config_entry.entry_id}"

    async def _async_setup(self) -> None:
        """Start watching the calendar file for changes."""
        if self.file_path is None:
            return
        self._file_mtime = await self.hass.async_add_executor_job(
            _mtime, self.file_path
        )
        self._unsub_file_check = async_track_time_interval(
            self.hass, self._async_check_file, FILE_CHECK_INTERVAL
        )

    async def _async_update_data(self) -> SchoolDayData:
        """Compute a fresh snapshot."""
        return self._compute()

    @callback
    def _compute(self) -> SchoolDayData:
        data = build_snapshot(self.calendar, dt_util.now())
        if self._unsub_transition is not None:
            self._unsub_transition()
        self._unsub_transition = async_track_point_in_time(
            self.hass, self._handle_transition, next_transition(data)
        )
        return data

    @callback
    def _handle_transition(self, _now: dt.datetime) -> None:
        self._unsub_transition = None
        self.async_set_updated_data(self._compute())

    @callback
    def async_set_calendar(self, calendar: SchoolCalendar) -> None:
        """Swap in a new calendar and refresh the entities."""
        self.calendar = calendar
        self.async_set_updated_data(self._compute())

    async def _async_check_file(self, _now: dt.datetime | None = None) -> None:
        """Reload the calendar file when it changed on disk."""
        assert self.file_path is not None
        mtime = await self.hass.async_add_executor_job(_mtime, self.file_path)
        if mtime == self._file_mtime:
            return
        self._file_mtime = mtime
        try:
            config = await self.hass.async_add_executor_job(
                load_school_file, self.file_path
            )
        except SchoolFileError as err:
            _LOGGER.error(
                "Not reloading %s, keeping the previous calendar: %s",
                self.file_path,
                err,
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self.issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key="invalid_file",
                translation_placeholders={
                    "name": self.config_entry.title,
                    "file": str(self.file_path),
                    "error": str(err),
                },
            )
            return
        ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
        _LOGGER.info("Reloaded %s", self.file_path)
        self.async_set_calendar(SchoolCalendar.from_config(config))

    async def async_shutdown(self) -> None:
        """Cancel timers."""
        if self._unsub_transition is not None:
            self._unsub_transition()
            self._unsub_transition = None
        if self._unsub_file_check is not None:
            self._unsub_file_check()
            self._unsub_file_check = None
        ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
        await super().async_shutdown()


def _mtime(path: Path) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None
