#!/usr/bin/env python3
"""Check a School Day calendar file without Home Assistant.

Prints the school days per month (compare them with the counts printed on most
district calendars) and warns about entries that are probably mistakes, such as
a holiday that falls on a weekend - a typical sign of a misread date.

Usage:
    pip install pyyaml voluptuous
    python3 scripts/check_calendar.py school_day/my_school.yaml

The file may hold one school, a calendar fragment, or a list of schools as in
configuration.yaml. ``!include`` is supported; ``!secret`` values are ignored.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import importlib.util
from pathlib import Path
import sys

try:
    import voluptuous as vol
    import yaml
except ImportError:
    sys.exit("Please install the dependencies first: pip install pyyaml voluptuous")

MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "school_day"
    / "model.py"
)
_spec = importlib.util.spec_from_file_location("school_day_model", MODEL_PATH)
assert _spec and _spec.loader
model = importlib.util.module_from_spec(_spec)
sys.modules["school_day_model"] = model
_spec.loader.exec_module(model)


class _Loader(yaml.SafeLoader):
    """SafeLoader with Home Assistant's !include and !secret tags."""


def _include(loader: _Loader, node: yaml.Node) -> object:
    base = Path(loader.name).parent
    with open(base / loader.construct_scalar(node), encoding="utf-8") as file:
        return yaml.load(file, _Loader)


_Loader.add_constructor("!include", _include)
_Loader.add_constructor("!secret", lambda loader, node: None)


def _weekday(date: dt.date) -> str:
    return date.strftime("%a")


def _fmt_range(rng: model.DateRange) -> str:
    if rng.is_single_day:
        return f"{rng.first} {_weekday(rng.first)}"
    return f"{rng.first} {_weekday(rng.first)} to {rng.last} {_weekday(rng.last)}"


def check(school: dict, title: str) -> bool:
    """Print a report for one school. Return False on errors."""
    print(f"\n=== {title} ===")
    try:
        config = model.validate_school(school)
        calendar = model.SchoolCalendar.from_config(config)
    except vol.Invalid as err:
        print(f"ERROR: {err}")
        return False

    for name, schedule in sorted(calendar.schedules.items()):
        print(f"Schedule {name:<16} {schedule.start:%H:%M} - {schedule.end:%H:%M}")
    week = ", ".join(
        f"{model.WEEKDAYS[day]}={name}" for day, name in sorted(calendar.week.items())
    )
    print(f"Week: {week}")

    warnings: list[str] = []
    periods = calendar.periods or []
    if not periods:
        warnings.append("no school_year given: every regular weekday is a school day")

    for period in periods:
        first, last = period.range.first, period.range.last
        label = f" ({period.name})" if period.name else ""
        print(f"\nSchool year{label}: {_fmt_range(period.range)}")
        per_month: Counter[str] = Counter()
        for info in calendar.iter_days(first, last):
            if info.school_day:
                per_month[info.date.strftime("%Y-%m %b")] += 1
        for month, count in sorted(per_month.items()):
            print(f"  {month}: {count:3d} school days")
        print(f"  Total:    {sum(per_month.values()):3d} school days")
        for date in (first, last):
            if not calendar.day(date).school_day:
                warnings.append(
                    f"{date} {_weekday(date)}: first/last day is not a school day"
                )

    def in_session(date: dt.date) -> bool:
        return not periods or any(date in p.range for p in periods)

    for entry in calendar.days_off:
        dates = list(calendar.iter_days(entry.range.first, entry.range.last))
        if all(info.date.weekday() not in calendar.week for info in dates):
            warnings.append(
                f"day off '{entry.name or ''}' {_fmt_range(entry.range)} only covers "
                "weekend days - is the date right?"
            )
        elif not any(in_session(info.date) for info in dates):
            warnings.append(
                f"day off '{entry.name or ''}' {_fmt_range(entry.range)} is outside "
                "the school year"
            )
    for entry in calendar.special_days:
        if not any(
            i.school_day
            for i in calendar.iter_days(entry.range.first, entry.range.last)
        ):
            warnings.append(
                f"special day '{entry.name or ''}' {_fmt_range(entry.range)} is not a "
                "school day, so it has no effect"
            )

    if calendar.special_days:
        print("\nSpecial days:")
        for entry in calendar.special_days:
            info = calendar.day(entry.range.first)
            times = f"{info.start:%H:%M}-{info.end:%H:%M}" if info.school_day else "-"
            print(f"  {_fmt_range(entry.range):<34} {times:<12} {entry.name or ''}")
    if calendar.days_off:
        print("\nDays off:")
        for entry in calendar.days_off:
            print(f"  {_fmt_range(entry.range):<34} {entry.name or ''}")
    if calendar.extra_days:
        print("\nExtra days:")
        for entry in calendar.extra_days:
            print(f"  {_fmt_range(entry.range):<34} {entry.name or ''}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")
    return True


def main() -> int:
    """Run the checker."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file", type=Path, help="calendar YAML file")
    args = parser.parse_args()

    with open(args.file, encoding="utf-8") as file:
        data = yaml.load(file, _Loader)
    if isinstance(data, dict) and "school_day" in data:
        data = data["school_day"]
    schools = data if isinstance(data, list) else [data]

    ok = True
    for index, school in enumerate(schools, 1):
        title = (school or {}).get("name") or f"{args.file.name} #{index}"
        ok &= check(school, title)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
