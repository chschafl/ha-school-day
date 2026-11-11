"""The School Day integration.

Schools can be set up two ways, both backed by YAML:

* UI: Settings > Devices & services > Add integration > School Day. You give the
  school a name and the integration reads the calendar from a YAML file in your
  config folder (a starter file is created for you). The file is watched and
  reloaded automatically when it changes.
* configuration.yaml: a list of schools under ``school_day:``. Each one is
  imported as a config entry; use the ``school_day.reload`` action after edits.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify
from homeassistant.util.hass_dict import HassKey
import voluptuous as vol

from .const import CONF_FILE, CONF_SCHOOL_ID, DOMAIN, SERVICE_RELOAD
from .coordinator import SchoolDayConfigEntry, SchoolDayCoordinator
from .loader import (
    InvalidPathError,
    SchoolFileError,
    load_school_file,
    resolve_path,
)
from .model import CONF_ID, SchoolCalendar, validate_school

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]

DATA_YAML_SCHOOLS: HassKey[dict[str, dict[str, Any]]] = HassKey(DOMAIN)


def _yaml_school(value: Any) -> dict[str, Any]:
    """Validate a school from configuration.yaml; it needs a name."""
    if not isinstance(value, dict) or not value.get(CONF_NAME):
        raise vol.Invalid("every school needs a 'name'")
    school = validate_school(value)
    school[CONF_ID] = slugify(school.get(CONF_ID) or school[CONF_NAME])
    return school


def _unique_ids(schools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    for school in schools:
        if school[CONF_ID] in seen:
            raise vol.Invalid(
                f"two schools share the id '{school[CONF_ID]}'; give one of them "
                "a different 'name' or an explicit 'id'"
            )
        seen.add(school[CONF_ID])
    return schools


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(_ensure_list, [_yaml_school], _unique_ids)},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Import schools from configuration.yaml and register the reload action."""
    await _async_sync_yaml_schools(hass, config.get(DOMAIN, []), create_now=False)

    async def _async_reload(call: ServiceCall) -> None:
        conf = await async_integration_yaml_config(hass, DOMAIN)
        if conf is None:
            return  # the config error has been logged already
        existing = [
            entry.entry_id for entry in hass.config_entries.async_entries(DOMAIN)
        ]
        await _async_sync_yaml_schools(hass, conf.get(DOMAIN, []), create_now=True)
        for entry_id in existing:
            if hass.config_entries.async_get_entry(entry_id) is not None:
                await hass.config_entries.async_reload(entry_id)

    async_register_admin_service(hass, DOMAIN, SERVICE_RELOAD, _async_reload)
    return True


async def _async_sync_yaml_schools(
    hass: HomeAssistant, schools: list[dict[str, Any]], *, create_now: bool
) -> None:
    """Make the config entries match the schools in configuration.yaml."""
    by_id = {school[CONF_ID]: school for school in schools}
    hass.data[DATA_YAML_SCHOOLS] = by_id

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.source != SOURCE_IMPORT:
            continue
        school = by_id.get(entry.data[CONF_SCHOOL_ID])
        if school is None:
            _LOGGER.info(
                "Removing %s, it is no longer in configuration.yaml", entry.title
            )
            await hass.config_entries.async_remove(entry.entry_id)
        elif entry.title != school[CONF_NAME]:
            hass.config_entries.async_update_entry(entry, title=school[CONF_NAME])

    for school_id, school in by_id.items():
        flow = hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={CONF_SCHOOL_ID: school_id, CONF_NAME: school[CONF_NAME]},
        )
        if create_now:
            await flow
        else:
            # Entries created during async_setup are set up once it finished.
            hass.async_create_task(flow)


async def async_setup_entry(hass: HomeAssistant, entry: SchoolDayConfigEntry) -> bool:
    """Set up a school from a config entry."""
    file_path = None
    if CONF_FILE in entry.data:
        try:
            file_path = resolve_path(hass.config.config_dir, entry.data[CONF_FILE])
            config = await hass.async_add_executor_job(load_school_file, file_path)
        except (InvalidPathError, SchoolFileError) as err:
            # Not ready (instead of failed) so Home Assistant keeps retrying and
            # picks up the fixed file without a manual reload.
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="invalid_file",
                translation_placeholders={
                    "file": entry.data[CONF_FILE],
                    "error": str(err),
                },
            ) from err
    else:
        config = hass.data.get(DATA_YAML_SCHOOLS, {}).get(entry.data[CONF_SCHOOL_ID])
        if config is None:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="not_in_yaml",
                translation_placeholders={"school_id": entry.data[CONF_SCHOOL_ID]},
            )

    coordinator = SchoolDayCoordinator(
        hass, entry, SchoolCalendar.from_config(config), file_path
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SchoolDayConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
