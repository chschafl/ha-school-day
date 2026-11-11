"""Fixtures for School Day tests."""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    return


SCHOOL_YAML = """
schedules:
  regular: { start: "08:50", end: "15:20" }
  early_release: { start: "08:50", end: "12:20" }
week:
  mon-thu: regular
  fri: early_release
school_year:
  from: 2026-09-02
  to: 2027-06-17
  name: "2026-27"
days_off:
  - { date: 2026-11-11, name: Veterans Day }
  - { from: 2026-11-26, to: 2026-11-27, name: Thanksgiving Break }
  - { from: 2026-12-21, to: 2027-01-01, name: Winter Break }
special_days:
  - { date: 2026-11-25, schedule: early_release, name: Day before Thanksgiving }
  - { date: 2026-11-18, start: "10:50", name: Late start }
extra_days:
  - { date: 2026-11-14, name: Saturday make-up }
"""
