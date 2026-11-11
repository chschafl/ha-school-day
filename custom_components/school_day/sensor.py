"""Sensors: start/end time, status, next school day and days left."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import datetime as dt
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATUSES
from .coordinator import SchoolDayConfigEntry, SchoolDayCoordinator, SchoolDayData
from .entity import SchoolDayEntity, day_attributes

PARALLEL_UPDATES = 0


def _days_left_attributes(data: SchoolDayData) -> dict[str, Any]:
    period = data.period
    return {
        "total": data.days_total,
        "school_year": period.name if period else None,
        "first_day": period.range.first.isoformat() if period else None,
        "last_day": period.range.last.isoformat() if period else None,
    }


@dataclass(frozen=True, kw_only=True)
class SchoolDaySensorDescription(SensorEntityDescription):
    """Describes a School Day sensor."""

    value_fn: Callable[[SchoolDayData], dt.datetime | dt.date | str | int | None]
    attributes_fn: Callable[[SchoolDayData], dict[str, Any]] | None = None


SENSORS = (
    SchoolDaySensorDescription(
        key="start_time",
        translation_key="start_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.start,
    ),
    SchoolDaySensorDescription(
        key="end_time",
        translation_key="end_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.end,
    ),
    SchoolDaySensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUSES,
        value_fn=lambda data: data.status,
    ),
    SchoolDaySensorDescription(
        key="next_school_day",
        translation_key="next_school_day",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: (
            data.next_school_day.date if data.next_school_day else None
        ),
        attributes_fn=lambda data: day_attributes(data.next_school_day),
    ),
    SchoolDaySensorDescription(
        key="school_days_left",
        translation_key="school_days_left",
        native_unit_of_measurement="days",
        value_fn=lambda data: data.days_left,
        attributes_fn=_days_left_attributes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SchoolDayConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    async_add_entities(
        SchoolDaySensor(entry.runtime_data, description) for description in SENSORS
    )


class SchoolDaySensor(SchoolDayEntity, SensorEntity):
    """A School Day sensor."""

    entity_description: SchoolDaySensorDescription

    def __init__(
        self,
        coordinator: SchoolDayCoordinator,
        description: SchoolDaySensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> dt.datetime | dt.date | str | int | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
