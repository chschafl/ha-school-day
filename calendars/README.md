# Sample calendars

Ready-made School Day calendars, one folder per school district.

| District | School year | File | School days |
| --- | --- | --- | --- |
| Lake Washington School District (WA, USA) | 2026-27 | [`lwsd/2026-27-elementary.yaml`](lwsd/2026-27-elementary.yaml) | 180 |
| Lake Washington School District (WA, USA) | 2026-27 | [`lwsd/2026-27-middle-school.yaml`](lwsd/2026-27-middle-school.yaml) | 180 |

> **Check before you rely on them.** Each file names its source calendar.
> Bell times can differ from school to school within a district, so compare
> `schedules` with your own school's bell times. Look for `CHECK:` comments
> too: they mark values the source calendar didn't state.

## Use a sample

**In the UI:** copy the file to your Home Assistant config folder, e.g.
`/config/school_day/kirkland_middle_school.yaml`, adjust the bell times, then
go to *Settings > Devices & services > Add integration > School Day* and enter
that path as the **Calendar file**. The name you enter in the UI is used; the
`name` in the file is ignored.

**In configuration.yaml:** copy the file into your config folder and include
it. Either use it as is:

```yaml
school_day:
  - !include school_day/lwsd-2026-27-middle-school.yaml
```

or give it your school's name and bell times. The included file's dates are
kept and your `schedules` win:

```yaml
school_day:
  - name: Kirkland Middle School
    calendar: !include school_day/lwsd-2026-27-middle-school.yaml
    schedules:
      regular: { start: "07:50", end: "14:25" }
```

**Next school year:** when the new calendar is out, list both files under
`calendar:` and they work side by side:
`calendar: [!include lwsd-2026-27-middle-school.yaml, !include lwsd-2027-28-middle-school.yaml]`.

## Add a calendar

1. Create it with the [AI prompt](../docs/ai-calendar-prompt.md) or by hand.
   Keep the header comment with the district, school year, grade level and a
   link to the source calendar.
2. Name it `<district>/<school year>-<level>.yaml`, e.g.
   `lwsd/2027-28-high-school.yaml`, and add it to the table above.
3. Run the checker and compare the per-month counts with the source calendar:

   ```bash
   python3 scripts/check_calendar.py calendars/lwsd/2027-28-high-school.yaml
   ```

4. Run `pytest`. Every file in this folder is validated by the tests.
