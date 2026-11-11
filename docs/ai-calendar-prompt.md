# Turn a school calendar into a School Day file with AI

Most districts publish their calendar as a one-page PDF or image, like the
[Lake Washington School District 2026-27 calendar](https://resources.finalsite.net/images/v1787679561/lwsdorg/eok5lsfktcue6muzply9/2026-27LWSD-one-page-calendar-English.pdf).
An AI assistant that can read PDFs or images (Claude, ChatGPT, Gemini, ...)
can turn it into a School Day file in a minute.

1. Open a new chat and attach the calendar PDF, a screenshot, or paste its URL
   or text.
2. Paste the prompt below.
3. Answer the assistant's questions (grade level, bell times). If you don't
   know the bell times yet, say so; it leaves `"??:??"` placeholders and Home
   Assistant will refuse to load the file until you fill them in.
4. Check the result:
   - Read the `# CHECK:` comments at the end.
   - Compare the school days per month with the calendar. Many calendars print
     them, and the assistant lists them too. Better still, run
     `python3 scripts/check_calendar.py your-file.yaml` from this repository;
     it computes the counts itself and warns about suspicious dates.
5. Save the file as `/config/school_day/<school>.yaml` and add the
   integration in the UI. Or paste it into `configuration.yaml` under
   `school_day:` (see the README).

> Grid calendars are easy to misread: a date can slip one column and land on
> the wrong weekday. The prompt makes the assistant write the weekday next to
> every date and cross-check day counts, which catches most of these errors.
> Still spend two minutes checking the result against the original.

---

## The prompt

````text
You are converting a school calendar into a configuration file for the Home
Assistant integration "School Day". The calendar is attached (PDF, image, web
page or text).

## Step 1 - Ask me first

Before writing any YAML, read the whole calendar including legends, keys,
footnotes and small print. Then ask me, in one message:

1. Which school year(s) to include, if the calendar covers more than one.
2. Which grade level(s) / school type this is for, if anything differs by grade.
   Common examples: kindergarten starting later, a different last day for
   seniors (grade 12), elementary-only conference days, or different
   early-release days for elementary, middle and high school. List the
   differences you found.
3. The regular start and end time of the school day ("bell times"), and the
   times for each kind of shortened or shifted day the calendar mentions
   (early release, late start, half day, two-hour delay, ...). Tell me which
   kinds you found and what the calendar says about them, e.g. "dismissal 2
   hours early". If the calendar states the times, propose them.
4. Any weekly pattern you noticed, e.g. "every Wednesday is early release" or
   "late start Mondays", and ask me to confirm it.

If I say I don't know a time, use the placeholder "??:??" for it and continue.
Never invent times.

## Step 2 - Write the YAML

Write ONE YAML document in exactly this format:

```yaml
# <School or district name> - <school year>, <grade level>
# Source: <calendar title / URL>
name: <School name>

# Bell times. "regular" is mandatory; add one entry per kind of special day.
# Times are quoted 24-hour "HH:MM".
schedules:
  regular:       { start: "08:50", end: "15:20" }
  early_release: { start: "08:50", end: "13:20" }
  late_start:    { start: "10:50", end: "15:20" }

# Regular school days of the week and the schedule each one uses.
# Use the short list form if all days use "regular": week: [mon, tue, wed, thu, fri]
week:
  mon-thu: regular
  fri: early_release

# First and last day of school for students (inclusive).
school_year:
  from: 2026-09-02   # Wed
  to: 2027-06-16     # Wed
  name: "2026-27"

# Weekdays inside the school year WITHOUT school for students.
days_off:
  - { date: 2026-09-07, name: Labor Day }                          # Mon
  - { from: 2026-12-21, to: 2027-01-01, name: Winter break }       # Mon-Fri

# School days with different times. Refer to a schedule by name, or override
# just "start" and/or "end".
special_days:
  - { date: 2026-11-25, schedule: early_release, name: Day before Thanksgiving }  # Wed
  - { from: 2026-11-16, to: 2026-11-20, schedule: early_release, name: Conferences }  # Mon-Fri

# Extra school days that would otherwise be off (e.g. a Saturday make-up day).
extra_days:
  - { date: 2027-03-13, name: Make-up day }  # Sat
```

Rules:

- Dates are ISO `YYYY-MM-DD`. Times are quoted strings `"HH:MM"` in 24-hour
  format. Never leave a time unquoted.
- After EVERY date or range, add a comment with the weekday(s), e.g. `# Mon` or
  `# Mon-Fri`. Work out the weekday from the date itself (not from where you
  think it sits in the grid) and check it matches the calendar. If they
  disagree, re-read the calendar and add a `# CHECK:` comment.
- `school_year`: the first and last day of instruction for the chosen grade.
  If the calendar covers several years, use a list of `from`/`to` entries.
  Southern-hemisphere or term-based schools (Term 1-4) use one entry per term.
- `days_off`: every weekday inside the school year when students have no
  school: holidays, breaks, teacher workdays, professional development /
  learning days, grading days, conference days without classes, district
  closures. Use one `from`/`to` range for consecutive days, even when it spans
  a weekend (a winter break is one entry). Do not list ordinary weekends. Do
  not list days outside the school year. Use the calendar's own wording for
  `name`.
- `special_days`: days with school but different hours: early release, early
  dismissal, half day, late start, delayed start, minimum day. Prefer
  `schedule: <name>` and define that schedule under `schedules`; use `start` /
  `end` only for one-off times. A day is EITHER a day off OR a special day,
  never both.
- Recurring weekly patterns belong in `week`, not in `special_days`.
- Snow days / make-up days: do NOT add potential make-up days as school days.
  List them as comments under `# Possible make-up days (add to extra_days if
  used):`. If the last day of school depends on snow days, add a `# CHECK:`.
- Events that don't change attendance or times (picture day, PTA meetings,
  report cards, sports) are left out.
- Grade-specific dates that don't apply to the chosen grade are left out; add
  a short comment so I know they exist.
- If something is ambiguous or unreadable, make your best guess and add a
  comment starting with `# CHECK:` explaining the doubt.
- Output only valid YAML in a single ```yaml code block. Allowed top-level keys:
  name, schedules, week, school_year, days_off, special_days, extra_days.

## Step 3 - Verify

After the YAML block, write:

1. A table of school days per month that your YAML produces, and the total.
   Count them: weekdays from `week` inside `school_year`, minus `days_off`, plus
   `extra_days`. If the calendar prints day counts per month or a total
   (e.g. "180 days"), put them next to yours and explain every difference.
2. A list of every `# CHECK:` item.
3. Anything on the calendar you deliberately left out.
````

---

## Tips

- **One district, several kids:** ask the assistant to produce the district
  dates once without bell times (leave `schedules` out), save it
  as `school_day/district-2026-27.yaml`, and reference it from each school with
  `calendar: !include district-2026-27.yaml`. See
  [`examples/configuration.yaml`](../examples/configuration.yaml).
- **Next school year:** when next year's calendar is published, run the
  prompt again and add the new file as a second calendar:
  `calendar: [!include district-2026-27.yaml, !include district-2027-28.yaml]`.
  Both years then work side by side and you never have to edit on 1 July.
- **Snow day today?** Add `- { date: 2027-01-12, name: Snow day }` under
  `days_off`. File-based schools reload within a minute, without a restart.
