# Feature Request — Overtime (OT) entries + copy-forward skips one-offs

**Submitted by:** Team lead
**Date:** 2026-11-26
**Status:** Delivered — `is_ot` flag on SHIFT, OT in both editors, OT chip
and hours split in the grid; copy-forward skips OT/PTO/UTO and refills from
the standing schedule (PRD FR-12 / FR-13)

---

## User stories

1. As a scheduler I want to record **overtime** as its own kind of entry,
   so that when I view the week I can tell OT apart from someone's regular
   shift.
2. As a scheduler, when I **copy a week forward**, I don't want last week's
   OT, PTO or UTO to repeat next week. Those were one-offs, so copying them
   creates OT nobody approved and leave nobody filed.

## Context

- OT is a timed block of work. It needs the same handling as a shift:
  start and end times, the overlap check, overnight blocks, the Manila
  view, and the coverage chart. The only differences are its label, how it
  is counted, and whether it is copied forward.
- Copy-forward used to copy every entry exactly as it was. PTO and UTO came
  along with it, so a week's leave showed up again the next week.
- Next week's real leave already has a home: the planned-leave registry
  (FR-002), which is applied on top of every week build.
- Each person's **standing schedule** already exists in code as the default
  template (`scheduler/templates.py`), which is used by
  *Apply default schedule*.

## Behaviour

### OT entries (FR-12)

- **Model:** OT is a `SHIFT` with `is_ot = 1`, not a new `entry_type`. Every
  shift rule applies to it unchanged, and the migration is one
  `ADD COLUMN` (schema v5) with no table rebuild. A CHECK constraint keeps
  `is_ot` on SHIFT rows only.
- **Adding OT:** the type pickers on Add Schedule and in the grid editor
  offer **SHIFT · OT · PTO · UTO · RD**. OT uses the same start and length
  pickers as a shift.
  - On Add Schedule, OT defaults to **adding beside** the day's shift
    (default start 5:00 PM, length 2h). *Replace the day* is still
    available.
  - In the grid editor, the button reads **➕ Add as OT**, and
    **Update** can turn an existing shift into OT or back.
- **Composition rules** (`apply_entry(mode="add", is_ot=True)`):
  - OT can't overlap the day's regular shift (the split-shift rule).
  - OT on a **rest day replaces the RD**, because working your rest day is
    what OT on that day means. The replaced RD is counted in
    `overwritten`.
  - OT on a **PTO/UTO day is rejected**. In a bulk apply, a single bad date
    fails the whole apply and nothing is written.
  - Only a SHIFT can be OT. PTO/UTO/RD with `is_ot` raise a
    `ValidationError`.
- **Viewing OT:**
  - Grid cell: a brand-blue chip with the times, `⏱ OT 3:00 PM–5:00 PM`.
    The chip wraps inside the day column. In the Manila view, an OT block
    that crosses midnight keeps the chip on both days.
  - Edit-mode cell label: `7:00 AM + OT 3:00 PM`.
  - Hours column: regular hours with OT on its own line, `40h` /
    `+ 4h OT` (`week_minutes_by_person(entries, ot=True)`).
  - Coverage chart: OT bars use the person's color, faded, with a dashed
    edge. The tooltip label starts with "OT".
  - Roster order ignores OT, so an early OT block doesn't move a person up
    the list.
- **Planned leave** still wins and wipes OT along with the shift.

### Copy-forward skips one-offs (FR-13)

- **Carried:** regular shifts and RD, which make up the standing pattern.
  Notes are copied too.
- **Not carried:** OT, PTO and UTO.
- **Days left empty:** a day that held only skipped entries (a PTO/UTO day,
  or an OT-only rest day) is **refilled from the person's standing day** in
  the default template. Split standing days are filled in full.
  - If the person isn't in the template, the day stays empty and is listed
    in the result (`CopyResult.unfilled`). The flash message names each
    one, for example "⚠️ No standing schedule, left empty: Ana Wed 12/02".
- **Then planned leaves are applied**, so next week's actual PTO/UTO comes
  from the leave registry.
- All of this still runs in **one transaction**: the copy, the refill and
  the leave overlay.
- Result message: "Copied … 32 entries. Left out 5 OT/PTO/UTO entries;
  3 day(s) set from the standing schedule."

## Definition of Done

- OT can be added from Add Schedule and from the grid editor, both beside a
  shift and on a rest day. It can be edited back to a regular shift.
- OT shows as a labelled chip with its times in Pacific and Manila views,
  the Hours column splits regular hours from OT, and the coverage chart
  marks OT bars.
- Copy-forward never carries OT/PTO/UTO. Days emptied by the skip get the
  standing schedule, or are reported when there isn't one. Planned leaves
  still override.
- The logic lives in `scheduler/`, with tests for: OT apply and overlap,
  RD replacement, PTO rejection with no partial write, the DB CHECK, update
  in both directions, leave overlay, hours split, segments, grid labels,
  copy skip and refill (shift, RD, overnight, split, leave-wins, unfilled).
  Full suite: 205 passing.

## Out of scope

- OT approval workflow, OT caps, or pay-rate rules (for example the PH
  rest-day premium). The tool records the schedule, not payroll.
- Marking that an OT block fell on a rest day. The RD is replaced, so the
  cell shows only the OT chip. This could become `⏱ OT (RD)` later if
  payroll needs it.
- Editing the standing schedule in the UI. It is still code
  (`DEFAULT_TEMPLATE`), so when someone's regular hours change, update it
  there or copy-forward will refill leave days with the old hours.
- Offset-forward (PRD FR-6) isn't built yet. When it is, it should use the
  same carry rule (`weeks.is_carried`).
