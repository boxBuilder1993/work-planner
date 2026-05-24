# Chat-Poller Design

**Status:** Groomed; not yet implemented.
**Last updated:** 2026-05-24.
**Supersedes:** the algorithm-dispatch model in `ai-poller/algo_*.py` for `@ai-*` chat interactions. Legacy algorithms remain in the repo behind a feature flag and may be retired later.

---

## Summary

Refocus the `ai-poller` from algorithm dispatch (SDLC / orchestrated / debate / decompose) to **chat-mention dispatch**. Users interact with AI by `@ai-<persona>`-mentioning in task comments; the poller detects mentions, dispatches a single chat-style invocation to `claude-proxy` on the user's Mac, captures the structured reply, and atomically posts it as a comment + updates task mental-model state.

Different `@ai-<persona>` tags route to different agent configurations (prompt + tool allowlist + model tier). Each task can have a per-task **workspace** (filesystem directory) the AI uses for any work that needs real files (cloning, building, generated artifacts).

---

## Goals

- **Conversational AI per task** — `@ai-*` mention → reply, threaded.
- **Multiple personas** — `@ai-engineer`, `@ai-planner`, `@ai-manager`, etc., each with its own prompt, tools, and model.
- **Persistent per-task workspace** for AI work that touches the filesystem.
- **Atomic side effects** — the AI generates content; the poller writes (comment + state) in one transaction.
- **No phone-side changes required** — phones post comments today; the new flow Just Works on existing surfaces.

## Non-goals (v1)

- Replacing the existing CRUD task / comment management.
- Multi-machine resilience (the AI runs on one Mac via the existing tunnel).
- Real filesystem sandboxing (use convention + light enforcement; revisit later).
- Phone-side UX additions (autocomplete, AI-typing indicator) — deferred.
- Observability infrastructure (basic logs only for v1; richer telemetry deferred).
- The actual prompt content (separate workstream led by user).

---

## Architecture

```
Phone Android app  /  Web  /  Mobile
       │
       ↓ HTTPS
Railway: Postgres + Go backend            ← tasks, comments, props
       ↑
       │ polls for `needs_ai_reply=true`
Railway: ai-poller (Python)               ← mention detection + dispatch
       │
       ↓ POST /run  (HTTPS, structured payload)
claude-proxy.shravan-box-builder.net      ← Cloudflare Tunnel
       │
       ↓
Mac · claude-proxy/proxy.py (port 8400)
       │
       ↓ spawns (subprocess cwd = workspace_path)
claude -p
   ├── --add-dir <workspace_path>
   ├── --allowed-tools <persona tool allowlist>
   ├── --model <persona.model>
   ├── --output-format json
   ├── --no-session-persistence
   ├── --strict-mcp-config --mcp-config <file>
   ├── --system-prompt-file <persona body>
   └── env: WORKPLANNER_WORKSPACE_PATH=<path>, ALGO_TASK_ID=<task_id>
       │
       ↓ uses (stdio MCP)
workplanner_server.py                     ← read tools, run_command (workspace-scoped)
       │
       ↓ HTTP (read-only ops; writes go via poller)
Railway backend
```

The proxy returns structured JSON to the poller. The poller posts the comment, merges context, and flips status.

---

## Concepts

### Personas

A persona is a `(prompt + tool allowlist + model + small policy bundle)` accessed via `@ai-<persona>` mention. Personas are markdown files with YAML frontmatter, hot-reloaded by the poller on each dispatch.

- **All personas can use all three context layers** (thread, workspace, mental model). Behavioral differences (planner doesn't touch files; engineer does) are expressed in the prompt, not in the infrastructure.

### Context layers

Three layers of persistent context, used by every persona:

| Layer | What | Where | Updated by |
|---|---|---|---|
| **Thread** | Comment history on the task | `comments` table (backend) | Users + AI replies |
| **Workspace** | Filesystem state — code, generated files, cloned repos | `~/.workplanner/workspaces/<task_id>/` on Mac | AI via `run_command` and built-in file tools |
| **Mental model** | Structured context (open questions, decisions, assumptions) | `task.props.ai_context` (backend JSONB) | AI explicitly via structured output |

These are complementary, not redundant.

### Workspace

Per-task working directory on the Mac. Empty by default — the AI does its own setup (`git clone`, `npm install`, `mkdir`, write files) as needed. Persists across AI invocations on the same task. Not auto-deleted in v1.

---

## Data model

### Backend additions

| Object | Field | Type | Notes |
|---|---|---|---|
| `comments` | `props` | `JSONB NOT NULL DEFAULT '{}'` | New column; one-off migration |
| `tasks.props` | `workspace_path` | `string` (nullable) | Lazy-populated on first AI dispatch for the task |
| `tasks.props` | `ai_context` | `object` (nullable) | Mental model maintained by AI |

### Reserved `comments.props` keys

| Key | Type | Meaning | Set by |
|---|---|---|---|
| `ai-comment-status` | string | `pending` \| `dispatched` \| `replied` \| `failed` | poller |
| `ai-error` | string | Short error description when status is `failed` | poller |
| `ai-retry-count` | int | Number of dispatch attempts (incremented on each retry) | poller |
| `ai-model` | string | Model identifier used (e.g. `claude-opus-4-7`) | poller (from proxy response) |
| `ai-prompt-version` | string | Version/hash of persona prompt used | poller |
| `ai-persona` | string | Persona handling this mention (e.g. `engineer`, `default`) | poller |
| `ai-tool-calls` | array | `[{tool, args_summary}]` summary for audit | poller (from proxy response) |
| `ai-duration-ms` | int | Wall-clock time of the dispatch | poller (from `claude -p` JSON `duration_ms`) |
| `ai-cost-usd` | float | API cost in USD | poller (from `claude -p` JSON `total_cost_usd`) |
| `ai-stop-reason` | string | Model's stop reason (e.g. `end_turn`) | poller (from `claude -p` JSON `stop_reason`) |
| `ai-tokens` | object | `{input, output, cache_read, cache_creation}` token counts | poller (from `claude -p` JSON `usage`) |

Status `ai-comment-status` is set on the **mention comment** (the one containing `@ai-*`), not on the AI's reply. The reply is a plain comment with `created_by="ai-<persona>"` and `parent_comment_id` set to the mention.

### `task.props.ai_context` shape

```yaml
# Standardized — every persona reads/writes these
goal: "Single-sentence restated objective for this task"
scope:
  in: [...]              # things this task will do
  out: [...]             # things explicitly out of scope
open_questions: [...]    # specific questions the AI needs answered (nullable / empty array)
current_step: "..."      # what's being done this turn (nullable; some personas/turns won't set)
next_step: "..."         # what's planned after this (nullable)

# Poller-stamped — AI does NOT write these
last_updated_by: "ai-<persona>"
last_updated_at: "<ISO timestamp>"

# Persona-specific — free-form, optional. Examples:
#   engineer:  files_of_interest, tests_run, last_commit_sha
#   planner:   decomposition, dependencies
#   reviewer:  findings, risk_level
```

**Key semantics:**

| Key | Type | When set / updated |
|---|---|---|
| `goal` | string | When the AI's understanding of the task crystallizes or shifts. Stable across turns once set. |
| `scope` | `{in: [], out: []}` | When scope is proposed and accepted, or when boundary discoveries arise. |
| `open_questions` | string[] | Added when AI hits ambiguity it can't resolve; removed once answered. |
| `current_step` | string \| null | Updated nearly every turn that does real work. |
| `next_step` | string \| null | Forward-looking soft commitment. The next dispatch's `current_step` should generally match the previous turn's `next_step`; deviation is fine but should be visible (not silently changed). |

**Merge semantics:** the poller performs a partial merge of `context_update` from AI output into the existing `ai_context`. **Top-level keys replace; arrays are replaced wholesale (no append).** To add to an array, the AI returns the full new array.

`decisions`, `working_assumptions`, and `blockers` are intentionally NOT standardized in v1 — decisions go to the KB via `store_knowledge` (or are visible in the thread); blockers can be expressed as `open_questions`; working assumptions can surface inline in `reply_text` or as `open_questions` ("I'm assuming X — confirm?"). Promote to standardized keys later if usage demands.

### `task.props.workspace_path`

String, absolute path on the Mac (e.g., `/Users/shravankumarsundar/.workplanner/workspaces/<task_id>`). `null` until first AI dispatch on the task creates the workspace.

**UI surfaces this field directly** (small "Workspace" line on the task view). The AI's reply text does not need to mention the path.

---

## Behavior specification

### Mention detection

Regex (case-insensitive): `@ai(?:-([a-z]+))?\b`

- `@ai` → routes to `default` persona
- `@ai-engineer` → routes to `engineer.md`
- Unknown persona → falls back to `default` (which may explicitly acknowledge the unknown persona in its reply)
- **First mention in a comment wins.** Additional mentions in the same comment are ignored.

### Dispatch flow

1. Poller queries `GET /comments?needs_ai_reply=true`.
2. For each candidate comment, poller checks task-level lock (any sibling comment on this task with `ai-comment-status=dispatched`?). If locked, skip — re-try next cycle.
3. Poller sets `mention.props["ai-comment-status"] = "dispatched"` (this is also the per-task lock).
4. If `task.props.workspace_path` is unset, poller instructs the proxy to ensure the workspace dir exists, then writes the path back to the task.
5. Poller builds the prompt (persona body + thread excerpt + task context + ai_context + workspace path) and POSTs to the proxy.
6. Proxy invokes `claude -p` (see Component responsibilities below).
7. Proxy returns structured JSON: `{reply_text, context_update, model, tool_calls}`.
8. Poller validates `reply_text`:
   - **Non-blank** → atomic transaction: insert comment + merge `context_update` into `task.props.ai_context` + set `mention.props["ai-comment-status"] = "replied"` + record `ai-model`, `ai-prompt-version`, `ai-persona`, `ai-tool-calls`.
   - **Blank/whitespace-only** → increment `ai-retry-count`, re-dispatch (up to 3 attempts total).
   - **Exhausted retries** → set `ai-comment-status = "failed"`, `ai-error = "empty_reply_after_retries"`.
9. Dispatch errors (proxy timeout, unparseable output, network) → same retry path, with an appropriate `ai-error`.

### Status state machine

```
       mention detected
              │
              ▼
        (no value)
              │
       poller picks up
              │
              ▼
         dispatched ────retry─┐
              │               │
       proxy returns          │
              │               │
        ┌─────┴─────┐         │
        │           │         │
     non-blank   blank        │
        │           │         │
        ▼           └─────────┘
     replied      (after 3 retries)
                       │
                       ▼
                    failed
```

There is no `pending` state in v1 — the poller transitions directly from "unset" to `dispatched`. (Reserved in the enum for future use.)

### Concurrency

**One AI invocation per task at a time.** The `dispatched` value on any mention comment for a task IS the lock; the poller refuses to dispatch a new mention for task T if any existing mention on T is `dispatched`. New mentions wait their turn.

This avoids two AI processes mutating the same workspace concurrently and serializes mental-model updates.

### AI output contract

`claude -p --output-format json` returns the model's final assistant message + metadata. The poller expects the final assistant message to be a **single JSON object** — no surrounding prose, no markdown code fences — of the form:

```json
{
  "reply_text": "Human-readable reply that becomes the comment body verbatim.",
  "context_update": {
    "current_step": "Investigating why test_jwt_verify is failing",
    "next_step": "Patch the signClaim issuer fallback if the bisect confirms",
    "open_questions": [
      "Should JWT_ISSUER be a required env var, or have a default fallback?"
    ]
  }
}
```

- **`reply_text`** (required, non-blank): posted as comment text verbatim. No truncation. Markdown OK if UI renders it.
- **`context_update`** (required, may be `{}`): partial-merged into `task.props.ai_context`. Top-level keys replace; arrays replaced wholesale.

The AI does **not** set `last_updated_by` / `last_updated_at`; the poller stamps those after merging.

**Failure modes (all retried up to 3, then marked `failed`):**

| Condition | `ai-error` |
|---|---|
| Final assistant text is not valid JSON | `malformed_output` |
| `reply_text` missing or blank/whitespace-only | `empty_reply` |
| `context_update` missing entirely (must be `{}` if empty) | `missing_context_update` |
| Proxy timeout / network error | `proxy_error` |

The structured-output requirement is enforced via the persona prompt (specifically `_shared/output_format.md`). If a particular persona finds the JSON-wrap-on-every-reply too brittle, the contract can be revisited.

---

## Component responsibilities

### Backend (Go, Railway)

- **Migration**: add `props JSONB NOT NULL DEFAULT '{}'` to `comments`.
- **Comment update endpoint**: accept partial `props` patches (merge semantics, not replace). Concurrent writes to different keys must not clobber each other.
- **New filter**: `GET /comments?needs_ai_reply=true` returning comments where:
  - text matches `@ai(-[a-z]+)?` (case-insensitive), AND
  - `props->>'ai-comment-status'` is `null` or `'pending'`, AND
  - (optional) `created_at > now() - interval '1 day'` for sanity.
- **Task field exposure**: ensure `task.props.workspace_path` is returned to clients so UIs can render it.

### ai-poller (Python, Railway)

- **Replace** the algorithm dispatch loop in `processor.py` with the chat-mention loop.
- **New files**:
  - `chat_handler.py` — the loop + dispatch + atomic write.
  - `chat_prompt.py` — pure prompt builder (no side effects, easy to test).
  - `persona_registry.py` — loads & caches persona configs from `ai-poller/personas/*.md`.
- **Feature flag** at the top of the loop: `if config.enable_chat_handler: chat_loop() else: legacy_algo_loop()`.
- **Per-task lock**: enforced via the `dispatched` status check before dispatch.
- **Atomic write**: comment insert + `ai_context` merge + status flip in one backend transaction (single API call recommended).

### claude-proxy (Python, Mac)

- **Receive** dispatch payload: `{prompt_system, prompt_user, persona_name, allowed_tools, workspace_path, model, timeout}`.
- **Ensure workspace** exists: `mkdir -p <workspace_path>` if absent.
- **Invoke** `claude -p` with:
  - subprocess `cwd=<workspace_path>` (no `--cwd` flag exists; set via `subprocess.run`/`Popen` cwd param).
  - `--add-dir <workspace_path>` — restricts built-in file tools to workspace.
  - `--allowed-tools <persona allowlist>`.
  - `--model <persona.model>`.
  - `--output-format json`.
  - `--no-session-persistence` — avoid saving every dispatch as a resumable session.
  - `--strict-mcp-config --mcp-config <file>` — load only the workplanner MCP; ignore user-level Claude Code MCP configs.
  - `--system-prompt-file <persona body with shared fragments inlined>`.
  - prompt argument: the per-invocation context block (XML).
  - env: `WORKPLANNER_WORKSPACE_PATH=<workspace_path>` — consumed by MCP for shell confinement.
  - env: `ALGO_TASK_ID=<task_id>` — already used by MCP for KB tagging.
- **Capture** `claude -p` JSON output (single-line JSON object). The proxy retains the full envelope as `metadata` on the `StatusResponse` (`{type, duration_ms, total_cost_usd, stop_reason, usage, modelUsage, ...}`) and extracts the `.result` field (a string containing the inner JSON `{reply_text, context_update}`) into `result`. **Double-parse pattern:** proxy parses the outer JSON; the poller parses `result` as inner JSON.
- **Forward to poller** via existing job/status pattern. `GET /status/{job_id}` returns `{status, result, error, runtime, metadata}`. The poller uses `metadata` to stamp `comments.props`: `ai-duration-ms`, `ai-cost-usd`, `ai-stop-reason`, `ai-tokens`.
- **Timeouts** at the proxy layer (suggest 5 min default; persona may override).

### MCP server (`claude-proxy/workplanner_server.py`, Mac)

- **No new tools.** All existing tools usable for the chat path *except* `add_comment`.
- **`add_comment` excluded** from chat persona allowlists (still callable by legacy algorithm tools if those persist).
- **`run_command` workspace confinement**:
  - Read `WORKPLANNER_WORKSPACE_PATH` env at startup.
  - Default `working_dir` to workspace if unspecified.
  - Reject if `working_dir` is set and not within workspace; return clear error string in the tool result.
  - (Optional, follow-on) reject commands with obvious escapes (`cd /`, absolute paths to system dirs). Best-effort.

---

## Persona system

### Registry location

`ai-poller/personas/`

```
ai-poller/personas/
  default.md            ← @ai (no suffix)
  manager.md            ← @ai-manager
  planner.md            ← @ai-planner
  engineer.md           ← @ai-engineer
  reviewer.md           ← @ai-reviewer
  _shared/              ← prompt fragments referenced via `includes`
    workspace_intro.md
    output_format.md
    anti_patterns.md
```

### Persona file format

```markdown
---
name: engineer
description: Implements code; uses workspace heavily.
model: claude-sonnet-4-6
tools:
  - get_task
  - get_subtasks
  - get_parent_chain
  - get_task_comments
  - search_tasks
  - query_knowledge
  - store_knowledge
  - create_task
  - run_command
reply_length_cap: 4000    # prompt-level guidance (not enforced by truncation)
includes:
  - _shared/workspace_intro.md
  - _shared/output_format.md
  - _shared/anti_patterns.md
---

You are a senior software engineer ...
```

### Routing rules

- `@ai` → `default`
- `@ai-<name>` → `<name>.md`
- Unknown `<name>` → `default` (which may surface the unknown persona in its reply)
- First mention wins; subsequent mentions in the same comment are ignored

### Hot reload

Personas are re-read on each dispatch (low frequency, cheap). No poller restart needed to iterate on prompts.

### Bootstrapping behavior is per-persona

Whether a persona proactively clones repos, installs deps, or sets up the workspace is decided in its prompt. Examples (informal):

- `default` — never bootstraps; stays conversational.
- `planner` — never touches filesystem.
- `engineer` — may bootstrap if the task description references a clonable repo.
- `reviewer` — assumes workspace is already populated.

These behaviors are not encoded in the persona config — only in the prompt body.

---

## Workspace model

### Path convention

`~/.workplanner/workspaces/<task_id>/`

### Lifecycle

- **Created** lazily, the **first time a persona is dispatched for the task**. The proxy `mkdir -p`s the directory; the poller writes the path back to `task.props.workspace_path`.
- **Reused** for all subsequent dispatches on the same task (any persona).
- **Persists** indefinitely. No auto-cleanup in v1.
- **Future:** consider archiving (`mv archive/<task_id>/<timestamp>/`) on task close.

### Confinement

| Layer | Mechanism | Strength |
|---|---|---|
| `claude -p` cwd | `--cwd <workspace>` | Biases default behavior |
| Built-in file tools | `--add-dir <workspace>` (no other dirs) | Strong for Read/Write/Edit/Glob/Grep |
| MCP `run_command` | env-based check (default cwd, reject out-of-scope `working_dir`) | Medium — bypassable via `bash -c` tricks |
| Prompt rule | Explicit "stay within `<workspace>`" instruction | Weak alone, useful in combination |

Not a real sandbox. Sufficient for personal use. Upgrade path if multi-user: `sandbox-exec` or a per-task Docker container.

### AI's responsibilities inside the workspace

- Bootstrap as needed (clone, install, write files) via `run_command` and built-in file tools.
- Use `git` for version control if relevant (the workspace is a normal directory; git is available).
- Reference workspace contents in replies if material (e.g., "I ran `npm test` and got these failures") — but don't paste path strings into chat (UI surfaces the path separately).

---

## Locked decisions

- `comments.props` JSONB column + reserved keys list (above).
- `tasks.props.workspace_path` (string) + `tasks.props.ai_context` (object).
- Status state machine: `(unset) → dispatched → replied | failed`, with `pending` reserved.
- Status lives on the mention comment, not the reply.
- AI's structured output: `{reply_text, context_update}`. Both required (use `{}` if no context update). `reply_text` posted as comment verbatim; blank → retry up to 3.
- Final AI output is a **single JSON object** — no surrounding prose, no markdown code fences.
- `context_update` merge semantics: partial merge, top-level keys replace, arrays replaced wholesale.
- Standardized `ai_context` keys: `goal`, `scope`, `open_questions`, `current_step`, `next_step`. Personas may add their own keys freely.
- Poller stamps `last_updated_by` and `last_updated_at` after merging; AI does not set them.
- AI does NOT have `add_comment`; poller posts replies.
- Always reply (no opt-out via the AI).
- Mention regex: `@ai(?:-([a-z]+))?\b`, case-insensitive. `@ai-*` only (no `@claude-*` etc.).
- First mention wins.
- Sequential dispatch per task (the `dispatched` status is the lock).
- All personas access all three context layers (thread, workspace, mental model).
- Persona registry: markdown + frontmatter in `ai-poller/personas/`.
- Workspace: `~/.workplanner/workspaces/<task_id>/`, lazy on first dispatch, never auto-deleted in v1.
- Workspace path surfaced via UI from `task.props.workspace_path`; AI replies don't need to mention paths.
- Bootstrapping behavior is prompt-level (per persona), not infrastructure.
- Confinement: cwd + `--add-dir` + env-based MCP check; no real sandbox in v1.
- Feature flag for cutover; legacy algorithm code parked, not deleted.

## Open decisions

None blocking implementation. Items to revisit after first deployment:

- Workspace cleanup / archival policy.
- Whether `default` persona handles general chat or routes to other personas.
- Whether to allow multiple parallel personas on one task (today: sequential).
- Observability schema (logs structure, optional `ai_dispatch_log` table).
- Phone-side UX additions (`@ai-` autocomplete, "AI thinking" indicator).

---

## Anti-patterns to avoid

- ❌ **AI calling `add_comment` to post its own reply.** Use poller-mediated atomic write so reply + state + ai_context land together. Prevents orphan dispatched states and constrains the AI's action surface.
- ❌ **Storing AI status in two places.** Canonical: `mention.props["ai-comment-status"]`. Do not infer from "is there a reply comment yet" — that's a denormalized derivation that drifts.
- ❌ **Pre-cloning repos or pre-installing tools in the workspace** from the poller/proxy side. AI does its own bootstrap; what to clone and when is part of prompt-level decision-making per persona.
- ❌ **Truncating the AI's reply** in the poller. `reply_text` is the comment body verbatim. If replies are too long, fix the prompt (`reply_length_cap` is guidance, not enforcement).
- ❌ **Posting the workspace path in every AI reply.** UI surfaces it from `task.props.workspace_path`. AI only mentions paths when materially relevant (e.g., "wrote results to `out/report.json`").
- ❌ **Adding new columns for every AI metadata field.** Use `comments.props` and `task.props` JSONB instead. Reserve key names in this doc.
- ❌ **Letting one task have multiple AI invocations concurrently.** The `dispatched` lock prevents this; don't bypass.
- ❌ **Multiple personas in one comment.** First mention wins. If you need coordination, that's what subsequent comments are for.

---

## Rollout plan

1. **Backend migration & filter** — add `comments.props` column, new filter endpoint. Deploy; legacy poller continues as-is (ignores new column).
2. **UI: surface `task.props.workspace_path`** on web / android / mobile task views. Small change per surface; no behavioral impact yet.
3. **Poller refactor behind feature flag** — implement `chat_handler.py`, `chat_prompt.py`, `persona_registry.py`. Flag default OFF. Test in isolation.
4. **Proxy + MCP updates** — `WORKPLANNER_WORKSPACE_PATH` env injection, `--cwd` / `--add-dir` plumbing, `run_command` workspace check, `claude -p --output-format json` parsing.
5. **Author the `default` persona** prompt (separate workstream). Validate end-to-end with a real `@ai` mention.
6. **Flip the feature flag** for chat handler. Legacy algorithm code remains parked.
7. **Iterate prompts** based on real chat interactions. Add `engineer`, `planner`, `manager`, `reviewer` personas as needed.
8. **Eventually:** retire `ai-poller/algo_*.py` and the workflow-specific MCP tools in `algo_server.py` if no longer used.

### Rollback

Flip the feature flag back. Poller resumes legacy algorithm dispatch. No data migration needed — the new `comments.props` column is harmless to legacy code.

---

## Related code

| Path | Role |
|---|---|
| `ai-poller/processor.py` | Existing dispatch loop; gets the chat-vs-legacy feature flag |
| `ai-poller/chat_handler.py` *(new)* | Chat dispatch loop |
| `ai-poller/chat_prompt.py` *(new)* | Prompt builder |
| `ai-poller/persona_registry.py` *(new)* | Loads & caches persona configs |
| `ai-poller/personas/` *(new dir)* | Persona definitions (markdown + frontmatter) |
| `ai-poller/algo_*.py` | Legacy algorithm code; parked, not deleted |
| `claude-proxy/proxy.py` | Receives dispatch, invokes `claude -p` with workspace plumbing |
| `claude-proxy/workplanner_server.py` | MCP server; `run_command` gains workspace enforcement |
| `claude-proxy/algo_server.py` | Legacy state-transition MCP; status TBD |
| `backend/internal/handler/comments.go` | Comment endpoints; gains `props` patch support + `needs_ai_reply` filter |
| `backend/internal/model/model.go` | Comment model; gains `Props` field |
| `backend/migrations/` *(new)* | Migration adding `comments.props` column |

---

## Out of scope (deferred)

- Persona prompt content (separate workstream led by user).
- Observability table schema / dashboards.
- Phone-side `@ai-` autocomplete or AI-typing indicators.
- Workspace cleanup / archival automation.
- Multi-machine resilience (e.g., AI workspace surviving Mac wipe via reconstitution from repo metadata).
- Hard filesystem sandboxing (`sandbox-exec`, Docker per-task).
- Parallel persona dispatch on one task.
- Reaction-based AI triggers (e.g., 👍 on a comment instead of `@ai`).
