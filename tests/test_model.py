"""Tests for the pure calendar model."""

from __future__ import annotations

import datetime as dt

import pytest
import voluptuous as vol
import yaml

from custom_components.school_day.model import (
    REASON_DAY_OFF,
    REASON_EXTRA_DAY,
    REASON_OUT_OF_SESSION,
    REASON_REGULAR,
    REASON_SPECIAL_DAY,
    REASON_WEEKEND,
    SchoolCalendar,
    parse_time,
    parse_week,
    validate_school,
)

from .conftest import SCHOOL_YAML


def build(text: str) -> SchoolCalendar:
    """Build a calendar from YAML text."""
    return SchoolCalendar.from_config(validate_school(yaml.safe_load(text)))


def d(value: str) -> dt.date:
    """Shorthand for a date."""
    return dt.date.fromisoformat(value)


def t(value: str) -> dt.time:
    """Shorthand for a time."""
    return dt.time.fromisoformat(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("08:30", "08:30"),
        ("8:30", "08:30"),
        ("08:30:00", "08:30"),
        ("3:20 PM", "15:20"),
        ("3:20pm", "15:20"),
        ("3 p.m.", "15:00"),
        ("12:00 am", "00:00"),
        ("12:15 PM", "12:15"),
        (510, "08:30"),  # YAML 1.1 reads unquoted 8:30 as 8 * 60 + 30
        (dt.time(7, 45), "07:45"),
    ],
)
def test_parse_time(value, expected) -> None:
    """Times are accepted in several notations."""
    assert parse_time(value) == t(expected)


@pytest.mark.parametrize(
    "value", ["TODO", "??:??", "25:00", "8", "13 pm", 30, True, 8.3]
)
def test_parse_time_invalid(value) -> None:
    """Invalid or ambiguous times are rejected."""
    with pytest.raises(vol.Invalid):
        parse_time(value)


def test_unquoted_yaml_times() -> None:
    """Unquoted 8:50 and 15:20 in YAML still work."""
    calendar = build("schedules:\n  regular: { start: 8:50, end: 15:20 }\n")
    info = calendar.day(d("2026-11-10"))
    assert (info.start, info.end) == (t("08:50"), t("15:20"))


def test_parse_week_forms() -> None:
    """Week accepts lists, ranges and mappings with inline times."""
    assert parse_week([" mon", "Tuesday", "WED"]) == {
        0: "regular",
        1: "regular",
        2: "regular",
    }
    assert parse_week("mon-fri") == dict.fromkeys(range(5), "regular")
    week = parse_week({"mon-thu": "regular", "fri": {"start": "08:00", "end": "12:00"}})
    assert week[3] == "regular"
    assert week[4].end == t("12:00")
    assert parse_week({"mon-fri": "regular", "wed": False}) == {
        0: "regular",
        1: "regular",
        3: "regular",
        4: "regular",
    }
    with pytest.raises(vol.Invalid):
        parse_week(["funday"])


def test_day_rules() -> None:
    """Each rule of the precedence order."""
    calendar = build(SCHOOL_YAML)

    # Before the school year.
    assert calendar.day(d("2026-09-01")).reason == REASON_OUT_OF_SESSION
    # First day, regular.
    first = calendar.day(d("2026-09-02"))
    assert first.school_day and first.reason == REASON_REGULAR
    assert (first.schedule, first.start, first.end) == (
        "regular",
        t("08:50"),
        t("15:20"),
    )
    # Fridays use the early_release schedule from the week.
    friday = calendar.day(d("2026-09-04"))
    assert (friday.schedule, friday.end) == ("early_release", t("12:20"))
    # Weekend.
    assert calendar.day(d("2026-09-05")).reason == REASON_WEEKEND
    # Single day off.
    vets = calendar.day(d("2026-11-11"))
    assert not vets.school_day
    assert (vets.reason, vets.label) == (REASON_DAY_OFF, "Veterans Day")
    # Range day off.
    assert calendar.day(d("2026-12-30")).label == "Winter Break"
    # Special day with a named schedule.
    special = calendar.day(d("2026-11-25"))
    assert (special.reason, special.label, special.end) == (
        REASON_SPECIAL_DAY,
        "Day before Thanksgiving",
        t("12:20"),
    )
    # Special day that only changes the start.
    late = calendar.day(d("2026-11-18"))
    assert (late.start, late.end) == (t("10:50"), t("15:20"))
    # Extra day on a Saturday.
    saturday = calendar.day(d("2026-11-14"))
    assert saturday.school_day and saturday.reason == REASON_EXTRA_DAY
    assert saturday.label == "Saturday make-up"
    # After the school year.
    assert calendar.day(d("2027-06-18")).reason == REASON_OUT_OF_SESSION


def test_precedence_overrides() -> None:
    """Extra days beat days off, days off beat special days, singles beat ranges."""
    calendar = build(
        """
schedules:
  regular: { start: "08:00", end: "15:00" }
  short: { start: "08:00", end: "12:00" }
days_off:
  - { from: 2026-12-21, to: 2027-01-01, name: Winter Break }
  - { date: 2026-11-18, name: Snow day }
special_days:
  - { from: 2026-11-16, to: 2026-11-20, schedule: short, name: Conferences }
  - { date: 2026-11-19, schedule: regular, name: Normal day }
extra_days:
  - { date: 2026-12-22, name: Make-up day }
  - { from: 2026-12-26, to: 2026-12-28, name: Make-up range }
"""
    )
    assert calendar.day(d("2026-12-22")).school_day
    assert calendar.day(d("2026-12-22")).label == "Make-up day"
    # Ranges in extra_days never turn a weekend into a school day.
    assert not calendar.day(d("2026-12-26")).school_day
    assert not calendar.day(d("2026-12-27")).school_day
    assert calendar.day(d("2026-12-28")).school_day
    # A day off wins over a special day.
    assert not calendar.day(d("2026-11-18")).school_day
    # The narrower special day refines the conference week.
    assert calendar.day(d("2026-11-17")).end == t("12:00")
    normal = calendar.day(d("2026-11-19"))
    assert (normal.end, normal.label) == (t("15:00"), "Normal day")


def test_no_school_year_means_always_in_session() -> None:
    """Without a school_year every regular weekday is a school day."""
    calendar = build("schedules:\n  regular: { start: '08:00', end: '15:00' }\n")
    assert calendar.day(d("2030-07-15")).school_day
    assert calendar.period_for(d("2030-07-15")) is None


def test_next_school_day_and_counts() -> None:
    """Next school day skips breaks; counting works."""
    calendar = build(SCHOOL_YAML)
    assert calendar.next_school_day(d("2026-12-18")).date == d("2027-01-04")
    assert calendar.next_school_day(d("2027-06-17")) is None
    assert calendar.count_school_days(d("2026-11-09"), d("2026-11-15")) == 5
    period = calendar.period_for(d("2026-07-01"))
    assert period is not None and period.name == "2026-27"


def test_calendar_fragments_merge() -> None:
    """A shared district calendar is merged with the school's own settings."""
    district = yaml.safe_load(
        """
schedules:
  regular: { start: "09:00", end: "15:00" }
  early_release: { start: "09:00", end: "12:00" }
school_year: { from: 2026-09-02, to: 2027-06-17 }
days_off: [2026-11-11]
special_days:
  - { date: 2026-11-25, schedule: early_release }
"""
    )
    next_year = yaml.safe_load(
        "school_year: { from: 2027-09-01, to: 2028-06-15 }\ndays_off: [2027-11-11]\n"
    )
    config = validate_school(
        {
            "name": "Middle school",
            "calendar": [district, next_year],
            "schedules": {"early_release": {"start": "07:50", "end": "11:20"}},
            "days_off": ["2026-10-09"],
        }
    )
    calendar = SchoolCalendar.from_config(config)
    assert not calendar.day(d("2026-11-11")).school_day
    assert not calendar.day(d("2026-10-09")).school_day
    assert not calendar.day(d("2027-11-11")).school_day
    assert calendar.day(d("2027-09-01")).school_day
    assert calendar.day(d("2026-11-25")).end == t("11:20")  # school overrides
    assert calendar.day(d("2026-11-24")).start == t("09:00")  # inherited


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{}", "uses schedule 'regular' which is not defined"),
        (
            "schedules: {regular: {start: '08:00', end: '15:00'}}\n"
            "special_days: [{date: 2026-11-25, schedule: early}]",
            "uses schedule 'early'",
        ),
        (
            "schedules: {regular: {start: '08:00', end: '15:00'}}\n"
            "special_days: [{date: 2026-11-25, end: '07:00'}]",
            "is not before end",
        ),
        (
            "schedules: {regular: {start: '08:00', end: '15:00'}}\n"
            "special_days: [{date: 2026-11-25}]",
            "needs 'schedule', 'start' or 'end'",
        ),
        (
            "schedules: {regular: {start: '08:00', end: '15:00'}}\n"
            "days_off: [{from: 2026-12-21, to: 2026-12-01}]",
            "is before 'from'",
        ),
        (
            "schedules: {regular: {start: '08:00', end: '15:00'}}\n"
            "days_off: [{date: 2026-12-21, from: 2026-12-21, to: 2026-12-22}]",
            "not both",
        ),
        (
            "schedules: {regular: {start: '15:00', end: '08:00'}}",
            "must be before end",
        ),
        (
            "schedules: {regular: {start: '08:00', end: '??:??'}}",
            "invalid time",
        ),
        (
            "schedules: {regular: {start: '08:00', end: '15:00'}}\n"
            "school_year: {date: 2026-09-01}",
            "use 'from' and 'to'",
        ),
        (
            "schedules: {regular: {start: '08:00', end: '15:00'}}\nholidays: []",
            "extra keys",
        ),
    ],
)
def test_validation_errors(text: str, message: str) -> None:
    """Configuration mistakes produce a helpful error."""
    with pytest.raises(vol.Invalid, match=message):
        validate_school(yaml.safe_load(text))


def test_example_files_are_valid() -> None:
    """The example files in the repository load with Home Assistant's YAML loader."""
    from pathlib import Path

    from homeassistant.util.yaml import load_yaml

    from custom_components.school_day import CONFIG_SCHEMA

    examples = Path(__file__).parent.parent / "examples"
    validate_school(load_yaml(examples / "simple-school.yaml"))
    CONFIG_SCHEMA(load_yaml(examples / "configuration.yaml"))
