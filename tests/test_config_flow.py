"""Tests for the UI set up of School Day."""

from __future__ import annotations

import os
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.school_day.const import DOMAIN

from .conftest import SCHOOL_YAML


@pytest.fixture
def config_dir(hass: HomeAssistant, tmp_path: Path) -> Path:
    """Use a temporary configuration folder."""
    hass.config.config_dir = str(tmp_path)
    return tmp_path


async def start_flow(hass: HomeAssistant, user_input: dict) -> dict:
    """Run the user step with the given input."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


async def test_creates_starter_file(
    hass: HomeAssistant, config_dir: Path, freezer: FrozenDateTimeFactory
) -> None:
    """Without a file, a starter file is written and the school is set up."""
    freezer.move_to("2026-11-10 10:00:00-08:00")
    result = await start_flow(hass, {"name": "Rose Hill Elementary"})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Rose Hill Elementary"
    assert result["data"] == {"file": "school_day/rose_hill_elementary.yaml"}
    assert result["description"] == "starter_file"
    starter = (config_dir / "school_day" / "rose_hill_elementary.yaml").read_text()
    assert "from: 2026-09-01" in starter
    assert "to: 2027-06-30" in starter
    assert (
        hass.states.get("binary_sensor.rose_hill_elementary_school_today") is not None
    )


async def test_existing_file(hass: HomeAssistant, config_dir: Path) -> None:
    """An existing valid file is used as is."""
    (config_dir / "calendars").mkdir()
    (config_dir / "calendars" / "lwsd.yaml").write_text(SCHOOL_YAML)
    result = await start_flow(hass, {"name": "Emma", "file": "calendars/lwsd.yaml"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"file": "calendars/lwsd.yaml"}
    assert result["description"] is None

    # The same file can't be added twice.
    result = await start_flow(hass, {"name": "Emma 2", "file": "calendars/lwsd.yaml"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_invalid_file(hass: HomeAssistant, config_dir: Path) -> None:
    """Errors in the file are shown in the form."""
    (config_dir / "bad.yaml").write_text("schedules:\n  regular: {start: '08:00'}\n")
    result = await start_flow(hass, {"name": "Emma", "file": "bad.yaml"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_file"}
    assert "required key not provided" in result["description_placeholders"]["error"]


@pytest.mark.parametrize("file", ["../outside.yaml", "/etc/passwd.yaml", "notes.txt"])
async def test_invalid_path(hass: HomeAssistant, config_dir: Path, file: str) -> None:
    """Only YAML files inside the config folder are allowed."""
    result = await start_flow(hass, {"name": "Emma", "file": file})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"file": "invalid_path"}


async def test_file_is_watched(
    hass: HomeAssistant, config_dir: Path, freezer: FrozenDateTimeFactory
) -> None:
    """Edits to the file are applied; broken edits raise a repair issue."""
    await hass.config.async_set_time_zone("America/Los_Angeles")
    freezer.move_to("2026-11-10 07:00:00-08:00")
    path = config_dir / "school.yaml"
    path.write_text(SCHOOL_YAML)
    entry = MockConfigEntry(domain=DOMAIN, title="Emma", data={"file": "school.yaml"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.emma_school_today").state == STATE_ON

    async def write(text: str, mtime: float) -> None:
        path.write_text(text)
        os.utime(path, (mtime, mtime))
        freezer.tick(31)
        async_fire_time_changed(hass, dt_util.utcnow())
        # The file check runs as a background task.
        await hass.async_block_till_done(wait_background_tasks=True)

    # Today becomes a day off.
    snow_day = "days_off:\n  - { date: 2026-11-10, name: Snow day }\n"
    await write(SCHOOL_YAML.replace("days_off:\n", snow_day), 1)
    today = hass.states.get("binary_sensor.emma_school_today")
    assert today.state == STATE_OFF
    assert today.attributes["label"] == "Snow day"

    # A broken edit keeps the previous calendar and raises a repair issue.
    await write("schedules: [oops", 2)
    assert hass.states.get("binary_sensor.emma_school_today").state == STATE_OFF
    issue_id = f"invalid_file_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    # Fixing the file clears the issue.
    await write(SCHOOL_YAML, 3)
    assert hass.states.get("binary_sensor.emma_school_today").state == STATE_ON
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_invalid_file(
    hass: HomeAssistant, config_dir: Path, freezer: FrozenDateTimeFactory
) -> None:
    """A broken file at start-up is retried until it is fixed."""
    entry = MockConfigEntry(domain=DOMAIN, title="Emma", data={"file": "missing.yaml"})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "does not exist" in entry.reason

    (config_dir / "missing.yaml").write_text(SCHOOL_YAML)
    freezer.tick(90)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.state is ConfigEntryState.LOADED
