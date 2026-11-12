# Changelog

## 0.1.0 - First release

**Is there school today?** School Day turns your school's calendar into Home
Assistant entities. Your automations then run only on real school days: wake-up
lights, "the bus leaves in 10 minutes" reminders, "pack your bag" the evening
before, pickup reminders on early-release days.

### Highlights

- **Entities for every school** (one device per school):
  - **School today** and **School tomorrow** (on/off). Their attributes give the
    reason (regular, special day, day off, weekend, ...), the label ("Winter
    Break"), the schedule and the times.
  - **Start time** and **End time** for today, as timestamps. Use them in time
    triggers with an offset, e.g. 40 minutes before school starts. On days
    without school they are `unknown`, so those automations don't fire.
  - **Status**: `before_school`, `in_school`, `after_school` or `no_school`.
    It changes exactly at the first and last bell.
  - **Next school day**, **School days left** and **School days completed**.
    Completed plus left always equals the year's total.
  - A **calendar** showing school days with their times and days off.
- **Simple YAML calendar format**:
  - Named bell schedules (`regular`, `early_release`, ...).
  - A weekly pattern, e.g. Wednesday early release.
  - The school year, days off, special days with different times, and extra
    days such as snow make-up days.
  - Clear rules decide what happens when entries overlap.
  - Schools can share one district calendar with `calendar: !include ...`, and
    you can list next year's calendar next to this one.
- **Two ways to set up**:
  - **UI:** enter a name. A commented starter file is created in
    `/config/school_day/`. It is watched, so saving it updates the entities
    within a minute, without a restart. A broken edit keeps the previous
    calendar and shows a repair issue.
  - **configuration.yaml:** each school still shows up as a device. Apply
    changes with the **School Day: Reload** action.
- **AI calendar prompt** ([docs/ai-calendar-prompt.md](docs/ai-calendar-prompt.md)).
  Attach your district's calendar PDF to Claude, ChatGPT or Gemini and get a
  ready-to-use file. It writes the weekday next to every date and cross-checks
  the school days per month.
- **Checker script** (`scripts/check_calendar.py`). It prints school days per
  month and warns about likely mistakes, such as a holiday on a Saturday. No
  Home Assistant needed.
- **Sample calendars**: Lake Washington School District 2026-27 for
  [elementary](calendars/lwsd/2026-27-elementary.yaml) and
  [middle school](calendars/lwsd/2026-27-middle-school.yaml). Both have 180
  school days.
- **Icon**: a school bell on school-bus yellow, shown by Home Assistant 2026.3
  and newer.
- **Translations**: English and German.

### Installation

**HACS:** add `https://github.com/chschafl/ha-school-day` as a custom
repository (category *Integration*), install **School Day**, then restart Home
Assistant.

**Manual:** copy `custom_components/school_day` to
`/config/custom_components/`, then restart.

Then go to **Settings > Devices & services > Add integration > School Day**.

Requires Home Assistant 2025.2 or newer.

### Example: bus reminder

```yaml
triggers:
  - trigger: time
    at:
      entity_id: sensor.kirkland_middle_school_start_time
      offset: "-00:40:00"
actions:
  - action: notify.mobile_app_kids_phone
    data:
      message: "🚌 The bus leaves in 10 minutes!"
```

### Good to know

- Bell times can differ between schools of the same district. Check the
  `schedules` in a sample calendar against your own school.
- The LWSD samples' half-day dismissal times aren't printed on the district
  calendar. They are marked `CHECK:`.
- Calendar event titles use the names from your file, with an English
  "No school –" prefix for days off; they aren't translated yet.

Feedback, bug reports and calendars for other districts are welcome:
<https://github.com/chschafl/ha-school-day/issues>
