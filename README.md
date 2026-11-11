<p align="center">
  <img src="images/icon.png" alt="School Day icon: a school bell on school-bus yellow" width="128">
</p>

# School Day for Home Assistant

Is there school today? When does it start, and when are the kids home?

School Day turns your school's calendar into Home Assistant entities, so your
automations only run on real school days: wake-up lights, "bus leaves in 10
minutes" reminders, "pack your bag" the night before, pickup reminders on
early-release days.

You describe each school in a small YAML file: the school year, the regular
school days and bell times, days off, and days with different times. An
[AI prompt](docs/ai-calendar-prompt.md) can write that file for you from your
district's calendar PDF.

> **How is this different from the built-in Workday integration?** Workday
> knows public holidays. School Day knows *school* calendars: breaks, teacher
> workdays, early releases, late starts, and the bell times for each day.

## Entities

Every school becomes a device with these entities (shown here for a school
named *Kirkland Middle School*):

| Entity | Example state | Description |
| --- | --- | --- |
| `binary_sensor.kirkland_middle_school_school_today` | `on` | Is there school today? |
| `binary_sensor.kirkland_middle_school_school_tomorrow` | `off` | Is there school tomorrow? Handy the evening before. |
| `sensor.kirkland_middle_school_start_time` | `2026-11-10T08:50:00-08:00` | Today's start time. `unknown` on days without school. |
| `sensor.kirkland_middle_school_end_time` | `2026-11-10T15:20:00-08:00` | Today's end time. `unknown` on days without school. |
| `sensor.kirkland_middle_school_status` | `before_school` | `before_school`, `in_school`, `after_school` or `no_school` |
| `sensor.kirkland_middle_school_next_school_day` | `2026-11-12` | The next school day after today. |
| `sensor.kirkland_middle_school_school_days_left` | `142` | School days left this school year (countdown to summer). |
| `sensor.kirkland_middle_school_school_days_completed` | `36` | School days completed so far this school year. |
| `calendar.kirkland_middle_school` | | School days with their times and days off, in the HA calendar. |

The two binary sensors (and *Next school day*) have attributes describing the
day:

| Attribute | Example | |
| --- | --- | --- |
| `reason` | `special_day` | `regular`, `special_day`, `extra_day`, `day_off`, `weekend`, `out_of_session` |
| `label` | `Day before Thanksgiving` | The `name` of the matching entry, if any |
| `schedule` | `early_release` | Which bell schedule applies |
| `start_time` / `end_time` | `08:50` / `12:20` | Times for that day |
| `date` | `2026-11-25` | The date described |

*School days left* and *School days completed* also have `total` (school days
in the year), `first_day`, `last_day` and `school_year`. Today counts as
completed once school is out, so completed + left always equals `total`. Compare `total` with your district's official
count (often 180 days) to sanity-check your calendar file.

## Installation

### HACS (recommended)

1. HACS > three-dot menu > **Custom repositories** > add
   `https://github.com/chschafl/ha-school-day` as an **Integration**.
2. Install **School Day** and restart Home Assistant.

### Manual

Copy `custom_components/school_day` into your `/config/custom_components/`
folder and restart Home Assistant.

## Setup

There are two ways to set it up. Both use the same YAML format.

### Option A: UI + calendar file (recommended)

1. **Settings > Devices & services > Add integration > School Day.**
2. Enter the school's name. Leave **Calendar file** empty to use
   `school_day/<school name>.yaml`.
3. If the file doesn't exist, School Day creates a commented **starter file**
   (Mon-Fri, 08:00-15:00, an estimated school year). Edit it with the
   *File editor* or *Studio Code Server* add-on, or replace it with the file
   the [AI prompt](docs/ai-calendar-prompt.md) generated.

The file is **watched**: save it and the entities update within a minute, with
no restart or reload. If you save a broken file, the previous version stays
active and a repair issue tells you what's wrong. If the file is broken when
Home Assistant starts, the school shows *Retrying setup* with the error until
the file is fixed.

You get UI management (device page, rename, disable, delete) while the
calendar data stays in a plain YAML file you can edit, version and share.

### Option B: configuration.yaml

```yaml
school_day:
  - name: Kirkland Middle School
    schedules:
      regular: { start: "08:50", end: "15:20" }
    school_year: { from: 2026-09-02, to: 2027-06-16 }
    days_off:
      - { date: 2026-11-11, name: Veterans Day }
```

or keep one file per school (each with a `name`):

```yaml
school_day: !include_dir_list schools/
```

Use a folder other than `school_day/`, which holds the files of schools added
in the UI.

Each school still appears as a device under *Devices & services*. After
editing, run **Developer tools > Actions > School Day: Reload** (or the
*School Day* entry on the **Developer tools > YAML** page). A school removed
from YAML is removed from Home Assistant.

## YAML reference

```yaml
name: Kirkland Middle School   # configuration.yaml only; in the UI the name is set there

# Bell times. "regular" is used on normal school days. Add as many named
# schedules as you need and refer to them below.
schedules:
  regular:       { start: "08:50", end: "15:20" }
  early_release: { start: "08:50", end: "13:20" }
  late_start:    { start: "10:50", end: "15:20" }

# Regular school days of the week. Default: mon-fri, all "regular".
week: [mon, tue, wed, thu, fri]
# ...or with a schedule per day (ranges like mon-thu work, inline times too):
# week:
#   mon-thu: regular
#   fri: early_release
#   wed: { start: "08:50", end: "13:20" }

# When school is in session (first and last day, inclusive). Use a list for
# several years or terms. Without it, every regular weekday is a school day.
school_year:
  from: 2026-09-02
  to: 2027-06-16
  name: "2026-27"            # optional

# No school. A bare date, a date with a name, or a from/to range.
days_off:
  - 2026-09-07
  - { date: 2026-11-11, name: Veterans Day }
  - { from: 2026-12-21, to: 2027-01-01, name: Winter break }

# School, but different times. Use a named schedule and/or override start/end.
special_days:
  - { date: 2026-11-25, schedule: early_release, name: Day before Thanksgiving }
  - { from: 2026-11-16, to: 2026-11-20, end: "12:00", name: Conference week }
  - { date: 2027-03-10, start: "10:50", name: Testing - late start }

# Extra school days that would otherwise be off, e.g. snow make-up days.
extra_days:
  - { date: 2027-03-13, name: Saturday make-up day }
  - { date: 2026-12-21, schedule: early_release, name: Make-up day in winter break }

# Shared calendars, merged into this school (see below).
calendar: !include district-2026-27.yaml
```

**Formats.** Dates are `YYYY-MM-DD`. Write times as quoted 24-hour `"HH:MM"`.
`"8:50 AM"` and `"3:20pm"` also work. Unquoted `8:50` works too, but quoting
avoids YAML surprises.

**How a date is decided** (first match wins):

1. In `extra_days` → **school**
2. In `days_off` → **no school**
3. Outside every `school_year` → **no school** (summer)
4. Weekday not in `week` → **no school** (weekend)
5. Otherwise → **school**, with the times from `week`

Times on a school day start from the weekday's schedule. A matching
`extra_days` entry, then any `special_days` entries, can change them. When
`special_days` entries overlap, the narrower one wins: a single date inside a
"conference week" range refines that one day. `special_days` never turn a day
off into a school day. Ranges in `extra_days` skip weekends; use a single
`date` for a Saturday make-up day.

**Shared district calendars.** Schools in one district share dates but not
bell times. Put the dates (`school_year`, `week`, `days_off`, `special_days`,
`extra_days`) in one file and include it from each school with `calendar:`.
Lists are combined; the school's own `schedules` and `week` win. Use a list to
include several years: `calendar: [!include 2026-27.yaml, !include 2027-28.yaml]`.
See [`examples/`](examples/).

## Let AI read your school calendar

Attach your district's calendar PDF to Claude, ChatGPT or Gemini and paste the
[School Day calendar prompt](docs/ai-calendar-prompt.md). It asks for the
grade level and bell times, writes the YAML with the weekday next to every
date, and cross-checks the number of school days per month.

Then double-check the result with the checker script (no Home Assistant
needed):

```bash
pip install pyyaml voluptuous
```

```bash
python3 scripts/check_calendar.py school_day/kirkland_middle_school.yaml
```

It prints school days per month and warns about likely mistakes, such as a
holiday that falls on a Saturday.

## Automation examples

**Bus reminder 40 minutes before school starts.** No condition is needed: on
days without school the start time is `unknown` and the trigger doesn't fire.

```yaml
automation:
  - alias: Bus reminder
    triggers:
      - trigger: time
        at:
          entity_id: sensor.kirkland_middle_school_start_time
          offset: "-00:40:00"
    actions:
      - action: notify.mobile_app_emmas_phone
        data:
          message: "🚌 The bus leaves in 10 minutes!"
```

**Wake-up light, school days only.**

```yaml
  - alias: Wake up for school
    triggers:
      - trigger: time
        at: "06:45:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.kirkland_middle_school_school_today
        state: "on"
    actions:
      - action: light.turn_on
        target: { entity_id: light.kids_room }
        data: { brightness_pct: 60, transition: 600 }
```

**The evening before: pack your bag, and a heads-up about special days.**

```yaml
  - alias: School tomorrow
    triggers:
      - trigger: time
        at: "19:30:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.kirkland_middle_school_school_tomorrow
        state: "on"
    actions:
      - action: notify.family
        data:
          message: >
            {% set t = states.binary_sensor.kirkland_middle_school_school_tomorrow.attributes %}
            🎒 School tomorrow, {{ t.start_time }}-{{ t.end_time }}.
            {% if t.label %}Note: {{ t.label }}.{% endif %}
```

**Pickup reminder that follows early release.**

```yaml
  - alias: Pickup reminder
    triggers:
      - trigger: time
        at:
          entity_id: sensor.kirkland_middle_school_end_time
          offset: "-00:20:00"
    actions:
      - action: notify.mobile_app_parent
        data:
          message: "Pickup at {{ states('sensor.kirkland_middle_school_end_time') | as_timestamp | timestamp_custom('%H:%M') }}"
```

**Status-based scenes.** `sensor.kirkland_middle_school_status` changes to
`in_school` at the first bell and `after_school` at the last. Use it to set the
house to "away", or start the robot vacuum while the kids are out.

## Icon

The icon is a school bell on school-bus yellow with the black rails of a school
bus. Home Assistant 2026.3 and newer show it from
`custom_components/school_day/brand/`. The source is
[`images/icon.svg`](images/icon.svg).

## Development

```bash
pip install -r requirements_test.txt
```

```bash
pytest
```

The calendar logic in [`model.py`](custom_components/school_day/model.py) is
plain Python with no Home Assistant imports, so it is easy to test and reuse.
