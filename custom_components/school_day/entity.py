"""Base entity for School Day."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SchoolDayCoordinator
from .model import DayInfo


class SchoolDayEntity(CoordinatorEntity[SchoolDayCoordinator]):
    """An entity belonging to one school."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SchoolDayCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="School Day",
            model="School calendar",
            entry_type=DeviceEntryType.SERVICE,
        )


def day_attributes(info: DayInfo | None) -> dict[str, Any]:
    """Describe a day for entity attributes."""
    if info is None:
        return {}
    return {
        "date": info.date.isoformat(),
        "reason": info.reason,
        "label": info.label,
        "schedule": info.schedule,
        "start_time": info.start.strftime("%H:%M") if info.start else None,
        "end_time": info.end.strftime("%H:%M") if info.end else None,
    }
