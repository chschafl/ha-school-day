"""Tests for School Day set up from configuration.yaml."""

from __future__ import annotations

from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
import yaml

from custom_components.school_day.const import DOMAIN

from .conftest import SCHOOL_YAML


def school(name: str = "Rose Hill", text: str = SCHOOL_YAML) -> dict:
    """Return a school definition as configuration.yaml would contain it."""
    return {"name": name, **yaml.safe_load(text)}


async def setup_yaml(hass: HomeAssistant, *schools: dict) -> None:
    """Set up the integration from YAML."""
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: list(schools)})
    await hass.async_block_till_done()


async def move_to(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: str
) -> None:
    """Move the clock and let scheduled callbacks run."""
    freezer.move_to(when)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


def state(hass: HomeAssistant, entity_id: str) -> str:
    """Return an entity's state."""
    entity = hass.states.get(entity_id)
    assert entity is not None, entity_id
    return entity.state


async def test_school_day_lifecycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """States follow the school day: before, in, after school, then midnight."""
    await hass.config.async_set_time_zone("America/Los_Angeles")
    freezer.move_to("2026-11-10 07:00:00-08:00")  # Tuesday
    await setup_yaml(hass, school())

    assert state(hass, "binary_sensor.rose_hill_school_today") == STATE_ON
    assert state(hass, "sensor.rose_hill_status") == "before_school"
    assert state(hass, "sensor.rose_hill_start_time") == "2026-11-10T16:50:00+00:00"
    assert state(hass, "sensor.rose_hill_end_time") == "2026-11-10T23:20:00+00:00"
    assert state(hass, "sensor.rose_hill_next_school_day") == "2026-11-12"

    today = hass.states.get("binary_sensor.rose_hill_school_today")
    assert today.attributes["reason"] == "regular"
    assert today.attributes["schedule"] == "regular"
    assert today.attributes["start_time"] == "08:50"

    tomorrow = hass.states.get("binary_sensor.rose_hill_school_tomorrow")
    assert tomorrow.state == STATE_OFF
    assert tomorrow.attributes["reason"] == "day_off"
    assert tomorrow.attributes["label"] == "Veterans Day"

    days_left = int(state(hass, "sensor.rose_hill_school_days_left"))
    total = hass.states.get("sensor.rose_hill_school_days_left").attributes["total"]
    assert 0 < days_left < total

    await move_to(hass, freezer, "2026-11-10 08:50:00-08:00")
    assert state(hass, "sensor.rose_hill_status") == "in_school"
    assert state(hass, "calendar.rose_hill") == STATE_ON

    await move_to(hass, freezer, "2026-11-10 15:20:00-08:00")
    assert state(hass, "sensor.rose_hill_status") == "after_school"
    assert state(hass, "calendar.rose_hill") == STATE_OFF
    assert int(state(hass, "sensor.rose_hill_school_days_left")) == days_left - 1

    # Midnight: Veterans Day, no school.
    await move_to(hass, freezer, "2026-11-11 00:00:00-08:00")
    assert state(hass, "binary_sensor.rose_hill_school_today") == STATE_OFF
    assert state(hass, "sensor.rose_hill_status") == "no_school"
    assert state(hass, "sensor.rose_hill_start_time") == STATE_UNKNOWN
    assert state(hass, "sensor.rose_hill_end_time") == STATE_UNKNOWN
    assert state(hass, "binary_sensor.rose_hill_school_tomorrow") == STATE_ON
    assert int(state(hass, "sensor.rose_hill_school_days_left")) == days_left - 1

    # Calendar shows the all-day "No school" event.
    calendar = hass.states.get("calendar.rose_hill")
    assert calendar.state == STATE_ON
    assert calendar.attributes["message"] == "No school – Veterans Day"


async def test_special_and_extra_days(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Special days change times, extra days add school on a weekend."""
    await hass.config.async_set_time_zone("America/Los_Angeles")
    freezer.move_to("2026-11-14 06:00:00-08:00")  # Saturday make-up day
    await setup_yaml(hass, school())

    today = hass.states.get("binary_sensor.rose_hill_school_today")
    assert today.state == STATE_ON
    assert today.attributes["reason"] == "extra_day"
    assert today.attributes["label"] == "Saturday make-up"

    await move_to(hass, freezer, "2026-11-18 06:00:00-08:00")  # late start
    assert state(hass, "sensor.rose_hill_start_time") == "2026-11-18T18:50:00+00:00"
    assert (
        hass.states.get("binary_sensor.rose_hill_school_today").attributes["reason"]
        == "special_day"
    )


async def test_calendar_events(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The calendar returns school days and days off."""
    await hass.config.async_set_time_zone("America/Los_Angeles")
    freezer.move_to("2026-11-20 12:00:00-08:00")
    await setup_yaml(hass, school())

    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": "calendar.rose_hill",
            "start_date_time": "2026-11-23T00:00:00-08:00",
            "end_date_time": "2026-11-30T00:00:00-08:00",
        },
        blocking=True,
        return_response=True,
    )
    events = response["calendar.rose_hill"]["events"]
    assert [(event["start"], event["summary"]) for event in events] == [
        ("2026-11-23T08:50:00-08:00", "Rose Hill"),
        ("2026-11-24T08:50:00-08:00", "Rose Hill"),
        ("2026-11-25T08:50:00-08:00", "Rose Hill – Day before Thanksgiving"),
        ("2026-11-26", "No school – Thanksgiving Break"),
    ]
    assert events[2]["end"] == "2026-11-25T12:20:00-08:00"
    assert events[3]["end"] == "2026-11-28"


async def test_reload_service(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """The reload action applies YAML changes, adds and removes schools."""
    await hass.config.async_set_time_zone("America/Los_Angeles")
    freezer.move_to("2026-11-10 07:00:00-08:00")
    await setup_yaml(hass, school())
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1

    changed = school(text=SCHOOL_YAML.replace('"08:50"', '"09:10"'))
    with patch(
        "homeassistant.config.load_yaml_config_file",
        return_value={DOMAIN: [changed, school("Redmond Middle")]},
    ):
        await hass.services.async_call(DOMAIN, "reload", blocking=True)
        await hass.async_block_till_done()

    assert state(hass, "sensor.rose_hill_start_time") == "2026-11-10T17:10:00+00:00"
    assert state(hass, "binary_sensor.redmond_middle_school_today") == STATE_ON
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2

    with patch(
        "homeassistant.config.load_yaml_config_file",
        return_value={DOMAIN: [school("Redmond Middle")]},
    ):
        await hass.services.async_call(DOMAIN, "reload", blocking=True)
        await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert [entry.title for entry in entries] == ["Redmond Middle"]
    assert entries[0].state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.rose_hill_school_today") is None


@pytest.mark.parametrize(
    "config",
    [
        {DOMAIN: [{"schedules": {"regular": {"start": "08:00", "end": "15:00"}}}]},
        {
            DOMAIN: [
                {"name": "A", "schedules": {"regular": {"start": "08", "end": "15"}}}
            ]
        },
        {DOMAIN: [school("Same"), school("Same")]},
    ],
)
async def test_invalid_yaml(hass: HomeAssistant, config: dict) -> None:
    """Invalid YAML configuration does not set anything up."""
    assert not await async_setup_component(hass, DOMAIN, config)
    assert hass.config_entries.async_entries(DOMAIN) == []
