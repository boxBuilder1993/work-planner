# Work Items

A `WorkItem` is the unit of AI execution. Every AI dispatch — whether
triggered by a user mention, a manager orchestration mention, or a future
periodic sweep — flows through this primitive. WorkItems give us:

- A single source of truth for dispatch state (replaces the brittle
  `comment.props.ai-comment-status` field that races with the dispatcher).
- A bounded, tracked retry loop (replaces today's retry-failed-forever
  candidate scan that burned ~$2 of compute today).
- A permanent record of every AI invocation (replaces ephemeral
  `task.props.ai_context` overwrites between persona dispatches).
- An audit-grade log of inputs + outputs per dispatch.

## Non-goals

- **No approval gates.** WorkItems are not PROPOSALs. They run as soon as
  they're created. Approval-of-engineer-work happens later, asynchronously,
  via comments and `@ai-manager review` mentions on the same thread.
- **No coordinator/sweep poller yet.** The first iteration only handles
  mention-triggered WorkItems. Sweep dispatch is a future layer that also
  produces WorkItems.

## Pipeline

```
[ comment with @ai-X mention ]
            │
            ▼
[ Poller 1: chat_handler ]  (modified)
   • Detects mention
   • Atomically creates WorkItem AND marks comment, server-side
   • Marks comment props.ai-comment-status = "enqueued",
                       props.ai-work-item-id = W
            │
            ▼
[ work_items table, status=pending ]
            │
            ▼
[ Poller 2: work_item_handler ]  (new)
   • Picks up pending + failed (where retry_count < max_retries)
   • Concurrency: max 2 in-flight per task; unbounded across tasks
   • Renders prompt, dispatches to claude-proxy
   • On success: writes output JSONB, status=completed
   • On failure: status=failed, retry_count++, last_error, attempts[] append
            │
            ▼
[ posts reply comment ]
   • parent_comment_id = triggering_comment_id  (threaded reply)
   • created_by = ai-<persona>
   • props.work_item_id = W
```

## Schema (`work_items`)

| column                   | type                                | notes                                                                 |
| ------------------------ | ----------------------------------- | --------------------------------------------------------------------- |
| `id`                     | UUID PK                             |                                                                       |
| `task_id`                | UUID FK → tasks                     | which task this WorkItem operates against                             |
| `triggering_comment_id`  | UUID FK → comments  (nullable)      | the mention that spawned it; null for future sweep-created items      |
| `target_persona`         | text                                | "engineer", "planner", "manager", "reviewer", "default"               |
| `prompt_context`         | JSONB                               | full rendered `{system, user, model, allowed_tools, max_turns}`       |
| `output`                 | JSONB (nullable)                    | `{reply_text, artifacts, metadata}` — filled on completion            |
| `status`                 | text                                | `pending \| dispatched \| completed \| failed \| cancelled`           |
| `retry_count`            | int default 0                       | incremented each failed dispatch                                      |
| `max_retries`            | int default 5                       | once retry_count == max_retries, no more auto-retries                 |
| `attempts`               | JSONB default `'[]'`                | per-attempt audit: `[{at, error, duration_ms, cost_usd}, …]`          |
| `last_error`             | text (nullable)                     | mirror of latest attempts[-1].error for quick filtering               |
| `created_at`             | int8                                | epoch ms                                                              |
| `updated_at`             | int8                                |                                                                       |
| `dispatched_at`          | int8 (nullable)                     |                                                                       |
| `completed_at`           | int8 (nullable)                     |                                                                       |
| `props`                  | JSONB default `'{}'`                | extensible                                                            |

Indexes:
- `(status, retry_count)` for poller's pickup query.
- `(task_id, status)` for per-task concurrency check and CLI listings.
- `(triggering_comment_id)` unique partial (`WHERE triggering_comment_id IS NOT NULL`) — guards idempotency.

## State machine

```
[create]                    → pending
pending                     → dispatched     (work_item_handler picks up)
dispatched → completed                       (output written; comment posted)
dispatched → failed                          (retry_count++; last_error set)
failed     → dispatched                      (next poll cycle, if retry_count < max_retries)
failed     → (terminal)                      (retry_count == max_retries; manual reset only)
any        → cancelled                       (PATCH from user/operator)
```

All transitions enforced server-side; invalid transitions rejected.

## Concurrency

- **Per task**: at most 2 WorkItems in `dispatched` state simultaneously.
  Poller picks up pending WorkItems only if `count(status='dispatched'
  AND task_id=this) < 2`.
- **Across tasks**: unbounded. Each task's queue is independent.

## Retry policy

- Failed WorkItems are auto-re-dispatched on every subsequent poll cycle
  until `retry_count == max_retries` (default 5).
- No backoff between retries — the proxy's runtime-degraded TTL gates
  rapid-fire by returning `no_runtime_available` until a real runtime is
  back. Add backoff later if this proves insufficient.
- After max retries: WorkItem stays `failed`. Manual unstick via
  `PATCH /api/internal/work-items/:id {retry_count: 0}` to reset, or
  `{status: cancelled}` to give up.
- Each retry appends to `attempts[]` with timestamp, error, duration, cost.

## Idempotency

Race scenario without protection: two chat_handler poll cycles see the
same un-marked mention within the window between WorkItem creation and
the comment-props PATCH; both create a WorkItem; one wins the
`comment.props.ai-work-item-id` update; the other's WorkItem is an
orphan that dispatches anyway.

**Fix**: WorkItem creation is a single backend transaction that:
1. Acquires a row lock on the triggering comment.
2. Checks `comment.props.ai-work-item-id IS NULL` — if not, returns
   the existing WorkItem id without creating.
3. Inserts the WorkItem.
4. Updates the comment's props with the new WorkItem id and
   `ai-comment-status=enqueued`.
5. Commits.

A unique partial index on `work_items.triggering_comment_id WHERE
triggering_comment_id IS NOT NULL` provides a second line of defense at
the DB level — even if the transaction logic above has a bug, the index
rejects duplicates.

## Endpoints

Internal (`/api/internal/work-items`, X-Internal-Key auth):

- `POST /work-items` — create. Returns existing if `triggering_comment_id`
  already mapped.
- `GET /work-items?task_id=&status=&persona=` — list/filter.
- `GET /work-items/:id` — fetch one.
- `PATCH /work-items/:id` — partial update (status, retry_count, props).
- `POST /work-items/:id/submit-output` — called by work_item_handler on
  successful AI reply. Body: `{output: {...}, metadata: {...}}`. Sets
  status=completed, completed_at.
- `POST /work-items/:id/record-attempt` — called on failure. Body:
  `{error, duration_ms, cost_usd}`. Appends to attempts[], increments
  retry_count, sets status=failed.

User-facing (`/api/work-items`, JWT auth) — read-only for v1. Write
mutations go through the internal API (operator tooling).

## MCP tools

Added to `claude-proxy/workplanner_server.py`:

- `get_my_work_item()` — returns the WorkItem the current dispatch is
  executing. Proxy injects `WORK_ITEM_ID` env into the MCP subprocess
  (same pattern as `WORKPLANNER_WORKSPACE_PATH`).
- `get_work_item(id)` — fetch by id.
- `list_work_items(task_id=None, status=None, persona=None)` —
  filter; defaults to the current task scope when `task_id` is omitted.

Existing tools unchanged.

## Output schema (`work_items.output`)

Inner JSON contract the AI emits, parsed by work_item_handler:

```json
{
  "reply_text": "<human-readable summary, posted as comment text>",
  "artifacts": {
    "branch": "ai/...",
    "commits": ["sha1", "sha2"],
    "files_changed": ["path/a.go", "path/b.py"],
    "tests": {"command": "go test ./...", "passed": true, "output": "..."},
    "build_status": {"passed": true},
    "scope_check": "stuck-to-asked | expanded-because-...",
    "open_questions": [],
    "confidence": "high | medium | low"
  },
  "context_update": { /* optional, merged into task.props.ai_context */ }
}
```

`artifacts` is required for engineer dispatches; optional for others
(planner/manager). The work_item_handler stores the entire output object
verbatim; `reply_text` is also lifted into the posted reply comment's
text.

## Persona changes (v1)

- **engineer**: prompt updated with the structured output schema above.
  Also told to call `get_my_work_item()` if it needs its assignment
  context, and `list_work_items(task_id=parent)` to see sibling work.
- **manager**: unchanged. Continues to orchestrate via `@ai-*` mentions
  in its replies. The chat_handler still routes those mentions into
  WorkItems just like user-authored mentions.
- **planner, reviewer**: no change for v1.

## Mention routing

Single-mention-per-comment, first-wins (regex `@ai(-[a-z]+)?` on the
comment text). Same as today. No change. We do not add structured
`target_persona` to comment props in v1.

## CLI (`wp work-items`)

Added in the same v1:

- `wp work-items list [--task T] [--status S] [--persona P]` — table view.
- `wp work-items show <id>` — full WorkItem detail (assignment + output + attempts).
- `wp work-items cancel <id>` — sets `status=cancelled`.
- `wp work-items retry <id>` — resets `retry_count=0` (allows another 5 attempts).

## Telemetry

Each `attempts[]` entry carries:

```json
{
  "at": 1780156000000,
  "error": "...",
  "duration_ms": 218000,
  "cost_usd": 0.534,
  "runtime": "claude",
  "model": "claude-sonnet-4-6",
  "stop_reason": "tool_use"
}
```

The successful attempt's metadata is stored on the WorkItem's `output`
JSON and also copied to the posted reply comment's props (for the UI's
benefit and so existing telemetry consumers keep working).

## Deploy plan

1. Backend: table + indexes + endpoints + state machine. Migration is
   add-only (no breaking changes to existing tables).
2. Poller: modify chat_handler to create-WorkItem-instead-of-dispatch.
   Add work_item_handler.
3. MCP: add three new tools.
4. Persona: bump engineer to v3 with the structured output contract.
5. CLI: `wp work-items` subcommands.
6. No data migration. Stuck failed comments will be auto-re-enqueued
   into WorkItems on the first cycle after deploy; bounded retries in
   the new system give them up to 5 fresh chances to succeed.

## Out of scope (future iterations)

- Coordinator / sweep poller (the periodic 5-min manager review pattern
  discussed earlier). Will produce WorkItems via the same primitive.
- Co-approval gates on assignment or output.
- Cross-task dependencies in the work_item_handler (today only the
  triggering comment links exist).
- UI surfaces (web/Android panels). v1 inspection is via `wp` CLI.
- Cancelling in-flight WorkItems (today cancel only affects pending or
  failed; dispatched ones finish naturally).
