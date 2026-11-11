"""Constants for the School Day integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "school_day"

# Config entry data
CONF_FILE: Final = "file"
CONF_SCHOOL_ID: Final = "school_id"

DEFAULT_FOLDER: Final = "school_day"

# How often a calendar file is checked for changes.
FILE_CHECK_INTERVAL: Final = timedelta(seconds=30)

SERVICE_RELOAD: Final = "reload"

STATUS_BEFORE_SCHOOL: Final = "before_school"
STATUS_IN_SCHOOL: Final = "in_school"
STATUS_AFTER_SCHOOL: Final = "after_school"
STATUS_NO_SCHOOL: Final = "no_school"
STATUSES: Final = [
    STATUS_BEFORE_SCHOOL,
    STATUS_IN_SCHOOL,
    STATUS_AFTER_SCHOOL,
    STATUS_NO_SCHOOL,
]
