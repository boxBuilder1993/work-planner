# Planner — Implementation Plan

The *what* lives in [PLANNER_DESIGN.md](PLANNER_DESIGN.md); this is the *how* —
phased PRs, each branch + CI-green before merge. Surfaces: **web + CLI** (no
Android). Engine lives in the **Go backend** so web and CLI share one schedule.

Critical-path spine: **PR1 → PR2 → PR3** gives a usable CLI planner; PR4–6 add
the web UI.

---

## PR #1 — Data-model foundation

**Goal:** all planner tables + task fields + CRUD API, no engine yet.

- **Migrations** (`backend/migrations/`):
  - `calendar`, `company_holidays`, `people`, `person_time_off` (see design doc)
  - `task_dependencies` (DAG)
  - `ALTER tasks`: `assignee_id`, `buffer_hours`, `remaining_effort`,
    `scheduled_start/end`, `actual_start/end`; extend `status` to allow
    `IN_PROGRESS`
  - reuse `duration` (→ estimate hours) + `due_date` (→ deadline)
- **Models** (`internal/model`): `Person`, `Calendar`, `CompanyHoliday`,
  `PersonTimeOff`, `TaskDependency`; add new task fields.
- **Store** (`internal/store`): CRUD for each; **cycle check** on dependency
  insert (topological test before commit).
- **Handlers** (`internal/handler`): REST endpoints — `/people`,
  `/calendar` + `/holidays`, `/time-off`, `/tasks/:id/dependencies`; surface
  new task fields on task GET/PATCH.
- **Tests** (integration): people CRUD; time-off ranges; dependency create +
  **cycle rejection**; task field round-trip.
- **Acceptance:** `make test-e2e` green (migrations apply); CRUD works; a
  dependency cycle is rejected with a clear error.

## PR #2 — Scheduling engine

**Goal:** generate the schedule from the data. The heart; unit-tested hard.

- **New package** (`internal/planner` or `internal/schedule`):
  - `availableHours(person, day)` — weekend/holiday/time-off resolution.
  - **List scheduler:** topo-sort leaves by deps → place each at
    `max(predecessor ends, assignee next-free)` across available hours →
    reserve assignee → roll up parents (+ `buffer_hours`) → mark
    `on_critical_path`.
  - Writes back `scheduled_start/end`; defaults `remaining_effort` from status.
- **Recompute trigger:** synchronous recompute after any mutation to tasks /
  deps / people / calendar (fine at single-manager scale); guard against
  redundant runs. Also a `POST /schedule/recompute` for explicit refresh.
- **Status transitions:** stamp `actual_start` on → in-progress,
  `actual_end` on → done.
- **Tests** (unit, deterministic fixtures): single chain; two ready tasks one
  assignee (serialized); weekend/holiday/OOO skipping; half-day OOO; parent
  buffer; critical-path correctness; cycle guard.
- **Acceptance:** fixture plans produce expected dates + critical path;
  recompute is idempotent.

## PR #3 — CLI planner support  *(usable end-to-end after this)*

**Goal:** drive the whole planner from `wp`.

- **Commands** (`cli/src/workplanner_cli`):
  - `wp person add|rm|list`, `wp person set-hours <id> <h>`,
    `wp person off <id> <start> <end> [--hours N]`
  - `wp calendar weekends ...`, `wp holiday add|rm|list`
  - `wp set <task> --estimate <h> --assignee <id> --buffer <h>`,
    `wp dep add|rm <task> <blocker>`
  - `wp tree` — add computed `start/end` columns
  - `wp schedule` — per-person execution view; `wp schedule --csv`
- **Tests** (`cli/tests`): command round-trips; CSV shape.
- **Acceptance:** build a plan, schedule it, export CSV — all from the terminal.

## PR #4 — Web: tree-table view

**Goal:** the editable WBS in the browser.

- **Web** (`web/src`): a Planner route — collapsible tree-table; inline edit of
  inputs (estimate, assignee, dep, buffer, priority, status); create subtask;
  computed columns (start/end, critical-path); depth control.
- API client additions; edit → triggers recompute → both columns refresh.
- **Acceptance:** inline edits persist and reflow; branches collapse/expand.

## PR #5 — Web: schedule view + CSV export + share

- **Web:** execution schedule view (per-person ordered queue + computed dates,
  group by project/person); **"Export CSV"** button; live **read-only exec
  mode** (shareable, shallow-zoom roll-up).
- **Acceptance:** schedule renders from computed data; CSV downloads
  (Sheets-import-ready); read-only link works.

## PR #6 — Web: people + calendar config

- **Web:** manage **people** (add/remove, hours), **time off** (ranges,
  half-day), and the shared **calendar** (weekends, company holidays).
- **Acceptance:** people/time-off/holiday CRUD from the web; changes reflow the
  schedule.

---

## Cross-cutting decisions

- **Recompute = synchronous on mutation** (single-manager scale). Revisit if it
  gets slow.
- **`on_critical_path`** computed during the scheduler run, stored alongside the
  dates (cheap, avoids recompute on read).
- **Cycle prevention** for dependencies enforced in the app/store layer.
- Each PR: own branch, tests for new code, CI green before merge.

## Deferred (post-v1)

Per-person working weeks (part-timers) · pinned/hard dates · risk register ·
templates/labels/attachments · capacity heatmap · named scenarios · PDF/slide
export · iCal/Google Calendar import · Android.
