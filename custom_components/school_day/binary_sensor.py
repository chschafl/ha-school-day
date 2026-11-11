"""Binary sensors: is there school today / tomorrow?"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SchoolDayConfigEntry, SchoolDayCoordinator, SchoolDayData
from .entity import SchoolDayEntity, day_attributes
from .model import DayInfo

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SchoolDayBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a School Day binary sensor."""

    day_fn: Callable[[SchoolDayData], DayInfo]


BINARY_SENSORS = (
    SchoolDayBinarySensorDescription(
        key="school_today",
        translation_key="school_today",
        day_fn=lambda data: data.today,
    ),
    SchoolDayBinarySensorDescription(
        key="school_tomorrow",
        translation_key="school_tomorrow",
        day_fn=lambda data: data.tomorrow,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SchoolDayConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_entities(
        SchoolDayBinarySensor(entry.runtime_data, description)
        for description in BINARY_SENSORS
    )


class SchoolDayBinarySensor(SchoolDayEntity, BinarySensorEntity):
    """On when the day is a school day."""

    entity_description: SchoolDayBinarySensorDescription

    def __init__(
        self,
        coordinator: SchoolDayCoordinator,
        description: SchoolDayBinarySensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return True if there is school."""
        return self.entity_description.day_fn(self.coordinator.data).school_day

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return why, and when."""
        return day_attributes(self.entity_description.day_fn(self.coordinator.data))
