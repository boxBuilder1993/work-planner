# Planner — Team Scheduling & Roadmap UI

## Summary

A friendly software-project-planning UI on top of the existing recursive task
model. The manager supplies **constraints** (breakdown, dependencies, effort,
assignee, calendars); the tool **generates the schedule** (dates,
critical path, end date) and renders it for both day-to-day project management
and read-only sharing with management. **You never type a date.**

The AI/persona layer (driver, comments) is intentionally out of scope for this
design — it coexists but is not a focus here.

## Core model: one recursive node

**Project = Task = Node.** No separate "project" or "quarter" entity. A
"project" is a node you've zoomed into; a "quarter" is just a date-range
viewport on a continuous timeline. Hierarchy (`parent_id`) is unbounded.

- **Uniform nodes.** Every node has the same fields — there is no leaf/parent
  *type*. A node's fields are **manager-input while it has no children** and
  become **computed rollups once it gets children** (estimate, dates, status roll
  up). The one exception is **buffer**, which a node with children may add on top.

## The working view: an editable tree-table (WBS)

Focus any node → see its sub-hierarchy as an indented, expand/collapse tree in
a single view.

- **Depth parameter** — show N levels; collapse beyond.
- **Inline editing** — edit a cell to change a field.
- **Create / extend / close** — "add child" on any row spawns a subtask and
  extends the tree; collapse to close a branch.

### Columns: input vs computed

| Input (manager) | Computed (engine, read-only) |
| --- | --- |
| Title, Description *(desc optional)* | Scheduled start / end |
| Estimate, in **hours** | On critical path? |
| Assignee | Calendar duration (effort over availability) |
| Dependencies (`blocked-by`) | Health (scheduled end vs due date) |
| Buffer *(optional)* | Remaining effort (from status) |
| Priority *(defaulted)* | Actual start / end (auto-stamped on status change) |
| Status (todo / in-progress / done) | Rolled-up estimate / dates / status *(nodes with children)* |
| Due date *(optional deadline)* | |

You never type a schedule date — the right column is generated and refreshes on
every edit. The only dates you enter are an optional **due date** (a deadline)
and, indirectly, **assignee availability** (the calendar).

### Uniform-node rules

- **Estimate / status:** taken from the manager on a **childless** node; once a
  node has children they **roll up** (estimate = sum, dates = span, status from
  children).
- **Assignee:** editable on any node. On a **childless** node it's the doer and
  drives scheduling + capacity; on a node **with children** it's the accountable
  owner (no effort, no capacity cost) and may cascade as the default for new
  children.
- **Buffer:** an optional reserve a node with children may add on top of its
  rollup. Effective end = `rolled-up children end + buffer`, advanced over the
  **team working calendar** (no assignee, so weekends/holidays apply, not
  anyone's OOO). It delays successors and the overall end date, and renders as a
  distinct buffer segment on the roadmap (contingency vs. real work).

## Scheduling engine: resource-constrained list scheduler

Deterministic and explainable (not a black-box optimizer). On every edit:

1. **Topologically order** leaves by dependencies (cycle-guarded).
2. For each leaf (childless node) in order, schedule at the **earliest feasible
   slot** = `max(latest predecessor end, assignee's next free time)`.
3. **Reserve** the assignee for `[start, start + effort]` advanced over their
   **availability calendar** (skip weekends, holidays, their OOO).
4. Roll leaf dates up into parents; apply parent buffers.

Falls out for free: concrete dates, **critical path**, project **end
date / makespan**, and per-person workload (each assignee's lane is their real,
conflict-free schedule; overload shows as a packed lane / late finish).

**Health:** when a node's computed `scheduled_end` exceeds its optional
**due date**, it's flagged at-risk / late. External unavailability is modeled by
editing **assignee availability**, never per-task date constraints.

## People & calendar model

Granularity is **hour-level**: effort is in hours, placed across working hours
(so half-day time off works). Deliberately simple — **no inheritance, no
composition**. Three concepts:

- **One shared calendar** — weekend definition + a company-holidays section.
  Applies to everyone.
- **Person** — working-hours config (theirs) + personal time off (OOO).

### Schema

```sql
-- One shared calendar: the company-wide non-working baseline
CREATE TABLE calendar (
    id           UUID PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    weekend_days SMALLINT NOT NULL DEFAULT 96,  -- bitmask Mon=1..Sun=64; Sat+Sun=96
    created_at   BIGINT NOT NULL,
    updated_at   BIGINT NOT NULL
);

CREATE TABLE company_holidays (
    id          UUID PRIMARY KEY,
    calendar_id UUID NOT NULL REFERENCES calendar(id) ON DELETE CASCADE,
    day         DATE NOT NULL,
    name        TEXT,
    created_at  BIGINT NOT NULL
);
CREATE UNIQUE INDEX company_holidays_unique_idx ON company_holidays (calendar_id, day);

CREATE TABLE people (
    id            UUID PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    email         TEXT,
    hours_per_day NUMERIC NOT NULL DEFAULT 8,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    BIGINT NOT NULL,
    updated_at    BIGINT NOT NULL
);

CREATE TABLE person_time_off (
    id         UUID PRIMARY KEY,
    person_id  UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    start_day  DATE NOT NULL,
    end_day    DATE NOT NULL,           -- inclusive
    hours_off  NUMERIC,                 -- NULL = full day(s) off; else partial/half-day
    note       TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);
```

### Resolution — `availableHours(person, day)`

```
if weekday(day) ∈ calendar.weekend_days   → 0      # weekend
if day ∈ company_holidays                 → 0      # company holiday
avail = person.hours_per_day
for each person_time_off covering day:
    hours_off IS NULL → return 0                    # full day off
    else avail -= hours_off                         # partial / half-day
return max(0, avail)
```

Adding time off reflows the plan automatically.

### Management surface (web + CLI)

The manager can **add / remove people** and manage each person's **time off**
(OOO) from the web (and equivalent CLI: `wp person add/rm`, `wp person off
<id> <range>`). Weekends + company holidays are edited on the single shared
calendar.

**Deferred:** per-person working weeks (part-timers off a weekday) — everyone
shares the weekend definition for now; add a per-person working-days override
later if needed.

## Two co-equal primary views

The same data is worked through two views, and an edit in either reflows both:

- **Hierarchical view** — the tree-table (WBS) above: structure + input editing
  + rollup. Where you *build* the plan.
- **Schedule view** — the dependency/availability timeline below: the
  *generated* execution schedule. Where you *see* when work happens and share it.

## The schedule view (dependency/availability timeline)

The generated execution schedule on a continuous timeline; "this quarter" is a
viewport, not an entity — scroll into the next quarter freely, nothing to roll
over. Bars come from the engine (dependencies + availability), so the view is
read/explore — editing constraints (e.g. assignee, dependencies, estimate)
happens in the tree-table or a detail panel, never by typing a schedule date.

- **Group by project** (hierarchy) or **by person** (swimlanes) — a toggle.
- Bars by computed dates; **dependency arrows**; **critical-path** highlight;
  buffer segments; OOO bands; **due-date markers**.
- **Exec / management mode:** live, read-only, shallow-zoom roll-up (top
  projects + dependencies + status + end date). Shareable.
- **CSV export** (in scope) — one row per leaf task (`path, title, assignee,
  estimate_hours, scheduled_start, scheduled_end, status, on_critical_path,
  due_date`), Google-Sheets-import-ready. CLI: `wp schedule --csv`; web:
  "Export CSV" button.

## Progress tracking (the living loop)

Planning is a cycle: capture → constrain → generate → balance → share →
**track → re-plan**. Tracking needs:

- **Status model** richer than PENDING/CLOSED: at least *not-started /
  in-progress / done*, ideally **remaining effort** so a half-done task
  reschedules only its remaining time. **The manager maintains status on every
  task** (single-writer — no per-assignee self-updates), same as all other
  inputs.
- **"Today" reflow:** completed work anchors at actual dates; unfinished work
  reschedules from now across remaining availability.
- **Health = due date vs. computed** (no baseline, since state is live): set an
  optional **due date** on a node; compare to its generated `scheduled_end` →
  on-track / at-risk / late.

## Data-model additions

| Concern | Addition |
| --- | --- |
| Dependencies | `task_dependencies` — `blocks` / `blocked-by` edges (DAG, cycle-guarded) |
| Assignee | `tasks.assignee_id` (FK → `people`, any node) |
| People & calendar | `people`, `person_time_off`, one shared `calendar` + `company_holidays` (see People & calendar model) |
| Buffer | `tasks.buffer` — optional reserve on nodes with children |
| Computed | `scheduled_start` / `scheduled_end`, `on_critical_path`, `actual_start` / `actual_end` |
| Progress | `status` (todo / in-progress / done) + computed `remaining_effort` |
| Deadline | optional `due_date` (reuse existing field) for health |

`duration` / time-taken already exists in the model.

## Manager / TPM capability set

Design assumption: **everything a manager + TPM does for project planning and
management is a first-class tool here.** ✓ = covered by the core design above;
+ = additional capability to include (post-core, but in scope).

**Plan & structure**
- ✓ Recursive WBS: inline edit, create/extend/collapse, depth control
- ✓ Estimates (hours), dependencies (DAG), parent buffers, due dates
- ✓ Priority (also the scheduler's tie-break)
- + Labels/tags, attachments & links (specs/docs), templates / clone-subtree, bulk multi-select edit

**Schedule & resources**
- ✓ Auto-generated schedule, critical path, project end date
- ✓ Resource calendars: working hours, holidays, per-person OOO (incl. half-day)
- ✓ What-if via instant recompute on every edit
- + Capacity/workload heatmap (who's over/under-allocated), named what-if scenarios

**Track & control**
- ✓ Status (todo/doing/done) + remaining effort, manager-maintained
- ✓ Today reflow; target-vs-computed health (on-track/at-risk/late); conflict/infeasibility surfacing
- + Risk register (risk flags + callouts surfaced on the roadmap)

**Views, reporting & sharing**
- ✓ Two co-equal views (hierarchical tree-table + dependency/availability schedule)
- ✓ Group by project / person; live read-only exec mode
- ✓ CSV export of the schedule (Google-Sheets-import-ready)
- + Saved views & filters (by person/status/priority/date), export (PDF/slides)

## Decisions (resolved)

1. **Granularity:** ✅ **Resolved: hour-level.** Effort in hours; scheduler
   places it across working hours; half-day OOO / partial availability
   supported.
2. **Owner scope:** ✅ **Resolved: editable on any node.** Leaf assignee drives
   scheduling/capacity; parent assignee is the accountable owner (optional
   cascade to children).
3. **Who updates progress:** ✅ **Resolved: manager-only.** The manager
   maintains status on all tasks (single-writer); assignees don't self-update.
4. **Calendar entry:** ✅ **Resolved: manual.** iCal / Google Calendar import
   is an optional later add, not part of the core.
