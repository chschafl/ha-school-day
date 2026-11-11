"""Loading school calendars from YAML files."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.yaml import load_yaml
import voluptuous as vol

from .model import validate_school


class SchoolFileError(Exception):
    """A calendar file is missing or invalid."""


class InvalidPathError(Exception):
    """A calendar file path is not allowed."""


def resolve_path(config_dir: str, file: str) -> Path:
    """Resolve a calendar file path relative to the config directory.

    Only ``.yaml``/``.yml`` files inside the config directory are allowed.
    """
    base = Path(config_dir).resolve()
    path = (base / file.strip()).resolve()
    if base not in path.parents or path.suffix.lower() not in (".yaml", ".yml"):
        raise InvalidPathError(file)
    return path


def load_school_file(path: Path) -> dict[str, Any]:
    """Load and validate a calendar file (runs in the executor)."""
    try:
        raw = load_yaml(path)
    except FileNotFoundError as err:
        raise SchoolFileError(f"{path} does not exist") from err
    except (HomeAssistantError, OSError) as err:
        raise SchoolFileError(str(err)) from err
    try:
        return validate_school(raw)
    except vol.Invalid as err:
        # str(err) gives the message and path without echoing the offending
        # value, which could be a secret if the wrong file was picked.
        raise SchoolFileError(str(err)) from err


def default_school_year(today: dt.date) -> tuple[dt.date, dt.date]:
    """Guess the current (northern hemisphere) school year for the starter file."""
    year = today.year if today.month >= 7 else today.year - 1
    return dt.date(year, 9, 1), dt.date(year + 1, 6, 30)


STARTER_TEMPLATE = """\
# School Day calendar for {name}
#
# Edit this file with your school's dates and times. Changes are picked up
# automatically within a minute - no restart needed.
#
# Reference: https://github.com/chschafl/ha-school-day#yaml-reference
# Tip: let an AI assistant fill this in from your school's calendar PDF:
#      https://github.com/chschafl/ha-school-day/blob/main/docs/ai-calendar-prompt.md
#
# Rules: dates are YYYY-MM-DD, times are quoted 24h "HH:MM".

# Bell times. "regular" is used on every normal school day.
schedules:
  regular: {{ start: "08:00", end: "15:00" }}
  # early_release: {{ start: "08:00", end: "12:00" }}

# Regular school days of the week.
week: [mon, tue, wed, thu, fri]

# First and last day of school. These are placeholders - please check them!
school_year:
  from: {first}
  to: {last}

# Days without school: holidays, breaks, teacher workdays, ...
days_off:
  # - date: {first_year}-11-11
  #   name: Veterans Day
  # - from: {first_year}-12-21
  #   to: {last_year}-01-01
  #   name: Winter break

# School days with different times: early release, late start, ...
special_days:
  # - date: {first_year}-11-25
  #   schedule: early_release
  #   name: Early release before Thanksgiving

# Extra school days, e.g. a snow make-up day.
extra_days:
  # - date: {last_year}-06-19
  #   name: Snow make-up day
"""


def write_starter_file(path: Path, name: str, today: dt.date) -> bool:
    """Create a starter calendar file if it does not exist yet.

    Returns True if a file was created (runs in the executor).
    """
    if path.exists():
        return False
    first, last = default_school_year(today)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        STARTER_TEMPLATE.format(
            name=name,
            first=first.isoformat(),
            last=last.isoformat(),
            first_year=first.year,
            last_year=last.year,
        ),
        encoding="utf-8",
    )
    return True
