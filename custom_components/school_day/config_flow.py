"""Config flow for School Day.

The UI only asks for a school name and the YAML file holding its calendar. If
the file doesn't exist yet, a commented starter file is created for the user to
edit. Schools defined in configuration.yaml are imported as entries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.util import dt as dt_util, slugify
import voluptuous as vol

from .const import CONF_FILE, CONF_SCHOOL_ID, DEFAULT_FOLDER, DOMAIN
from .loader import (
    InvalidPathError,
    SchoolFileError,
    load_school_file,
    resolve_path,
    write_starter_file,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Optional(CONF_FILE): str,
    }
)


def default_file(name: str) -> str:
    """Return the default calendar file for a school name."""
    return f"{DEFAULT_FOLDER}/{slugify(name) or 'school'}.yaml"


class SchoolDayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for School Day."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the school name and calendar file."""
        errors: dict[str, str] = {}
        placeholders = {"error": "", "folder": DEFAULT_FOLDER}

        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            file = (user_input.get(CONF_FILE) or "").strip() or default_file(name)
            try:
                path = resolve_path(self.hass.config.config_dir, file)
            except InvalidPathError:
                errors[CONF_FILE] = "invalid_path"
            else:
                file = path.relative_to(
                    Path(self.hass.config.config_dir).resolve()
                ).as_posix()
                await self.async_set_unique_id(f"file:{file}")
                self._abort_if_unique_id_configured()
                created = await self.hass.async_add_executor_job(
                    write_starter_file, path, name, dt_util.now().date()
                )
                try:
                    await self.hass.async_add_executor_job(load_school_file, path)
                except SchoolFileError as err:
                    errors["base"] = "invalid_file"
                    placeholders["error"] = str(err)
                else:
                    return self.async_create_entry(
                        title=name,
                        data={CONF_FILE: file},
                        description="starter_file" if created else None,
                        description_placeholders={"file": file},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Create an entry for a school defined in configuration.yaml."""
        await self.async_set_unique_id(f"yaml:{import_data[CONF_SCHOOL_ID]}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=import_data[CONF_NAME],
            data={CONF_SCHOOL_ID: import_data[CONF_SCHOOL_ID]},
        )
