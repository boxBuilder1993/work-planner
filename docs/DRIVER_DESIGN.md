# Driver — Autonomous Task Orchestration

## Summary

The **driver** is a periodic orchestrator that keeps an AI-monitored task
moving toward completion *without the user acting as a message courier*.
Every 5 minutes, for each task flagged `aiMonitoring`, a driver agent reads
the comment thread, decides the single next step, and acts on it — asking a
specialist persona a question, asking the user a question, or closing the
task when it's done.

This is the "future periodic sweep" anticipated in
[WORK_ITEMS_DESIGN.md](WORK_ITEMS_DESIGN.md): a coordinator layer that
produces WorkItems. It extends the existing chat/WorkItems production path
(`enable_chat_handler=true`). It does **not** reuse the legacy
algorithm/SDLC path or the `aiStatus` flags — all coordination state lives
in **comments + task status**.

## Goals

- A monitored task drives itself: plan → work → review → done, with the
  human as a *checkpoint* (define intent, sign off, unblock), not a relay.
- One unambiguous orchestrator and one unambiguous "are we done?" judge.
- Minimal new machinery — reuse WorkItems, personas, the mention scanner,
  and comments.

## Non-goals

- No `aiStatus` state-machine flags. Task `status` (PENDING/CLOSED) +
  comments are the only coordination state.
- No revival of the legacy `algo_*` / SDLC dispatch path.
- No free-for-all mesh. The topology is a star: the driver orchestrates;
  every other persona is a leaf.

## Relationship to the existing framework

| Concern | Mechanism | Reuse / New |
| --- | --- | --- |
| Driver dispatch + reply + retries | `work_item_handler` (`target_persona="driver"`) | Reuse |
| Driver's `@ai-<persona>` questions → specialists | `chat_handler` mention scan | Reuse, unchanged |
| Persona definition | `personas/driver.md` via `persona_registry` | Reuse mechanism |
| Heartbeat enqueue | new stage in `processor._run_chat_cycle` | **New** |
| `aiMonitoring` flag | `task.props` (no migration) | **New** |
| Driver-item dedupe + cadence | `work_items.idempotency_key` unique index | **New** |
| Dispatch authority | gate in `store.go` → `user` OR `ai-driver` | **Edit** |
| Termination | driver `wp close` + `aiMonitoring=false` | Reuse status |

## Role map

| Role | Job | Triggered by | Model |
| --- | --- | --- | --- |
| **driver** | Control flow: read thread → route / ask user / close | heartbeat (system) | cheap (sonnet/haiku) |
| **pm** | Draft definition of done / scope ("what/why") | driver | — |
| **manager** | Independent critic: *ratify* the DoD, *judge* completion | driver | opus |
| **planner** | Decompose / sequence work | driver | — |
| **engineer** | Implement; attach test/CI results to the thread | driver | — |
| **reviewer** | Focused code/diff review | driver | — |
| **user** | Define intent at start; sign off / unblock on escalation | — | — |

Authority is published once in `personas/_shared/chain_of_command.md`,
included by every persona: *the driver orchestrates, the manager judges,
the user is the ultimate authority; specialists answer and report.*

## The `aiMonitoring` flag

A **control flag** (user intent), not a state flag — stored in
`task.props.aiMonitoring`. Set `true` to have the driver keep driving the
task; the driver sets it `false` when it closes the task, and the user can
toggle it off anytime to pause. The heartbeat keys on
`aiMonitoring == true && status != CLOSED`.

**User-settable on both clients, and the *only* AI control.** The legacy AI
UI block — the `aiEnabled` toggle, the "AI Algorithm" picker, and the
algorithm/`aiStatus` badges — is **removed** from web and Android. In its
place, a single `aiMonitoring` toggle in the task editor, read/written
through `task.props.aiMonitoring`. (No new API: both clients already patch
`props` via `update_task`.) `aiEnabled` remains in the data model but is no
longer surfaced to users; the comments framework keys off `aiMonitoring`.

## Heartbeat + idempotency key (the core)

Each poll cycle, for every `aiMonitoring`, non-closed task, the poller
*attempts* to create a driver WorkItem with:

```
idempotency_key = "driver:" + task_id + ":" + floor(now_ms / 300000)
```

`300000` ms = a 5-minute bucket. A unique index on
`work_items.idempotency_key` makes the DB reject any second insert for the
same `(task, bucket)`. This single key does **two** jobs:

1. **Cadence** — at most one driver run per task per 5-minute window,
   regardless of how often the poll loop actually runs. The enqueue loop
   stays dumb ("try to enqueue all monitored tasks"); the DB enforces the
   rhythm.
2. **Dedupe** — concurrent or overlapping ticks can't stack two drivers on
   one task (the failure mode: two drivers independently picking different
   "next steps" → double-dispatched specialists / forked thread).

Driver WorkItems have `triggering_comment_id = NULL` (they're sweep-created,
per the WorkItems schema), so they fall outside the existing
`triggering_comment_id` idempotency index — hence the separate key.

## Driver behavior

On each run the driver reads the task + full comment thread and does
**exactly one** of:

1. **Needs a specialist** → post `@ai-<persona> <question>` (dispatched by
   the existing mention scan; includes `@ai-manager` for DoD review or a
   completion verdict).
2. **Needs the user** → post a question addressed to the user with **no
   `@ai` mention** (inert — the gate ignores it; it simply waits). This is
   the escalation / "input-required" path, expressed purely as a comment.
3. **Done** → the manager has confirmed completion → post a summary,
   `wp close` the task, set `aiMonitoring=false`.
4. **Already waiting** on an unanswered question (to a persona or the user)
   → no-op this tick.

The driver never judges "done" itself (that would be self-review of its own
orchestration) — it routes the completion question to the manager and acts
on the verdict. The driver is the **only** persona that closes tasks.

## Dispatch gate change

`store.go` `ListCommentsNeedingAIReply` currently dispatches comments
authored by `user` OR `ai-manager`. The driver becomes the sole
orchestrator, so:

```sql
-- before
AND (c.created_by NOT LIKE 'ai-%' OR c.created_by = 'ai-manager')
-- after
AND (c.created_by NOT LIKE 'ai-%' OR c.created_by = 'ai-driver')
```

The manager is demoted to a specialist: it posts verdicts that the driver
reads on the next tick; its own comments no longer fan out.

## Definition-of-Done contract flow

The DoD lives in the thread as ratified comments — no schema for it.

```
driver (fresh monitored task)
  └─ @ai-pm  draft the definition of done for this task
        pm posts DoD ─────────────────────────────────────┐
driver (next tick)                                         │
  └─ @ai-manager  review/ratify this DoD                   │
        manager ratifies (or sends back, or driver         │
        escalates to user if ambiguous) ──────────────────►│  ratified DoD = the contract
driver
  └─ @ai-planner / @ai-engineer  do the work
        engineer attaches test/CI results to the thread
driver
  └─ @ai-manager  does the work meet the DoD?  (judged
        against attached results, NOT self-report)
        manager: DONE ──► driver closes + aiMonitoring=false
        manager: NOT DONE ──► driver routes the gaps
```

Splitting *draft* (pm) from *ratify + judge* (manager) keeps the manager's
verification independent: it judges against an artifact it reviewed but did
not author.

## Correctness guardrails (MAST-aligned)

- **Termination owner** — the manager judges done; the driver closes.
  Counters "unaware of termination."
- **Independent verification** — pm drafts DoD, manager ratifies/judges;
  manager never self-reviews its own plan.
- **Ground truth over self-report** — the completion verdict is anchored on
  attached test/CI results, not the engineer's narration. *(Requires the
  engineer to attach results; can land as a fast-follow.)*
- **Bounded runaway** — the 5-minute bucket caps drive frequency; the human
  escape hatch is a no-`@ai` comment the driver recognizes and waits on.
- **Structural roles** — close permission is deliberate: only the driver
  closes; reviewer/manager stay read-only.

## Changes by file

| File | Change |
| --- | --- |
| `docs/DRIVER_DESIGN.md` | this doc |
| `backend/internal/store/store.go` | gate → `ai-driver`; `idempotency_key` insert/conflict |
| `backend/.../migrations` | `work_items.idempotency_key` + unique index |
| `backend/internal/handler/internal.go` | `create_work_item` accepts `idempotency_key` |
| `ai-poller/processor.py` | heartbeat stage in `_run_chat_cycle` |
| `ai-poller/api_client.py` | list `aiMonitoring` tasks; create driver WorkItem w/ key |
| `ai-poller/personas/driver.md` | new persona (cheap model) |
| `ai-poller/personas/manager.md` | reviewer that ratifies DoD + judges completion |
| `ai-poller/personas/_shared/chain_of_command.md` | new shared include |
| `ai-poller/personas/{planner,reviewer,engineer}.md` | close-permission cleanup |
| `web/src/components/TaskForm.tsx` (+ `types.ts`, `api/tasks.ts`) | remove legacy AI block; add `aiMonitoring` toggle via `props` |
| `app/.../ui/taskdetail/components/TaskInfoSection.kt` (+ `Task.kt`, DTO mapper) | remove legacy AI block (toggle/picker/badges); add `aiMonitoring` Switch via `props` |

## Open decisions

1. **`aiMonitoring` storage** — ✅ **Resolved: `task.props`** (no migration).
   Promote to a first-class column later only if heartbeat scanning needs an
   indexed filter.
2. **Bucket size** — 5 min (`300000` ms) is the starting cadence; it's a
   single constant to tune.
3. **DoD bootstrap** — if a fresh task has no DoD, the driver's first action
   is to ask the user (or `@ai-pm`) for it rather than guessing.
4. **Ground-truth anchoring (engineer attaches CI)** — ✅ **Resolved:
   fast-follow.** Ships as a separate PR after the core driver loop is live.
