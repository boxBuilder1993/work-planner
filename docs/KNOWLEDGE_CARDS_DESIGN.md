# Knowledge Cards

A simple, searchable company knowledge base for the AI personas (and for
humans). A **card** is a chunk of freeform text with tags. Personas read
cards to ground their work; humans author and curate them.

Work-list: [KNOWLEDGE_CARDS_TASKS.md](KNOWLEDGE_CARDS_TASKS.md).

## Scope — deliberately minimal

Started with an elaborate schema (types, authority lifecycle, supersession,
answer/body split) and cut it back to the essentials. A card is just:

- `id` — a short human slug (`auth-jwt-flow`), so cards can reference each
  other inline and humans can address them.
- `content` — freeform text. Any references (to other cards, URLs, files)
  live *inside* the text; we don't model them as structured fields.
- `tags` — for filtering.
- `is_valid` — a boolean so a human can retire a card without deleting it.
  Invalid cards are excluded from search by default.

That's it. No type enum, no authority states, no supersession chains, no
versioning. Add structure later only if a real need forces it.

## What we are NOT building (and why)

- **No vector store / ChromaDB for v1.** The corpus is bounded and
  hand-authored. Postgres full-text search + tag filtering covers it. Add
  `pgvector` only if the corpus ever outgrows that.
- **No new MCP tool.** Office infosec gates new MCP tools. Personas read
  cards via (1) pre-dispatch injection by the poller over plain HTTP, and
  (2) the existing shell capability calling `wp knowledge search`. Neither
  adds a reviewable tool surface.
- **No raw-code caching.** Agents navigate code live (grep/read) — always
  current. Cards capture *understanding*, not the code itself.

## Data model

```sql
CREATE TABLE knowledge_cards (
    id          TEXT PRIMARY KEY,        -- short slug: "auth-jwt-flow"
    content     TEXT NOT NULL,           -- freeform text; references inline
    tags        TEXT[] NOT NULL DEFAULT '{}',
    is_valid    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  BIGINT NOT NULL,
    updated_at  BIGINT NOT NULL
);
CREATE INDEX knowledge_cards_tags_idx  ON knowledge_cards USING GIN (tags);
CREATE INDEX knowledge_cards_fts_idx   ON knowledge_cards
    USING GIN (to_tsvector('english', coalesce(content,'')));
CREATE INDEX knowledge_cards_valid_idx ON knowledge_cards (is_valid);
```

- `id` is an author-provided slug (PK). Renaming breaks inline references —
  rare, deliberate.
- Full-text search is over `content` (the only text field). `ts_rank` for
  relevance ordering.
- `is_valid` default true; search filters `is_valid = true` unless the
  caller opts into invalid (human curation).

## API (internal-key auth)

```
POST   /api/internal/knowledge-cards            create {id, content, tags}
GET    /api/internal/knowledge-cards            list   (?tag=, ?includeInvalid=)
GET    /api/internal/knowledge-cards/search     ?q=<phrase>&tag=<t>&includeInvalid=
GET    /api/internal/knowledge-cards/:id        get one
PATCH  /api/internal/knowledge-cards/:id        edit (content, tags, isValid)
DELETE /api/internal/knowledge-cards/:id        delete
```

- **`search`** runs FTS over `content` (ranked) and/or filters by `tag`;
  either or both. Excludes invalid by default. `limit` param (default 10).
- All internal-key. The `wp` CLI (which holds your internal key) is the
  human + engineer search surface for v1.
- A **user-facing JWT read mirror** (`GET /api/knowledge-cards`,
  `/search`, `/:id`) is a trivial future add when a web UI needs it. Cards
  are company-global (no per-user scoping).

## Consumption — agentic pull (no MCP, no injection)

Personas retrieve cards **themselves, on demand**, as a required
due-diligence step — rather than the poller guessing relevance and pushing
cards in. Agentic pull gives better relevance (the agent knows its own
task), keeps context lean (no irrelevant cards diluting attention), and
lets the agent iterate (search → read → search again). This mirrors how
agents already navigate *code* (grep/read on demand) — we extend the same
philosophy to knowledge.

**Mechanism (no new MCP tool — infosec-friendly):**

- Every persona that does substantive work gets a **scoped Bash
  capability** limited to the knowledge CLI: `Bash(wp knowledge:*)`. They
  can run `wp knowledge search "..."` and `wp knowledge show <id>` and
  nothing else — no `rm`, no `curl`, no filesystem. Engineer already has
  full Bash; manager and planner get this narrow grant. Per-persona
  `tools:` frontmatter is the existing scoping mechanism (it becomes
  `--allowedTools`), so this is a one-line addition per persona.
- `wp` is installed + configured in the dispatch environment. The proxy
  exports `WP_BASE_URL` / `WP_INTERNAL_KEY` (from its `WORKPLANNER_API_URL`
  / `INTERNAL_API_KEY`) into the agent's environment so `wp knowledge`
  authenticates without a config file.
- A shared persona instruction makes KB search a **required first step**:
  search before proposing / deciding / implementing, read the relevant
  cards, and state what was found (or that nothing relevant exists).
  `max_turns` is raised so personas can afford the lookups (cost is a
  non-issue on the Max subscription).

Personas are told: cards orient you, but live code/systems are ground
truth — verify specifics against them when correctness matters.

**Optional enhancement — card catalog (unknown-unknowns).** Pure pull only
finds what the agent thinks to search for. A lightweight catalog (just
`id` + `tags` + a one-line summary per card) injected into every prompt
lets the agent see *what knowledge exists*, then pull the full content of
what it needs. Small, cacheable, low attention cost. Deferred unless recall
proves weak in practice.

## Write access

Cards are written by **humans** (via `wp knowledge`) and by the **archivist**
— and by nobody else. The working personas (engineer, manager, planner,
reviewer, default) are **read-only**: their `wp knowledge` grant is scoped to
`search`/`show`/`list`, and the shared fragment tells them not to write. A
persona that spots something worth recording says so in its reply; the
archivist folds it in.

## Archivist — automated knowledge maintenance

The archivist is a dedicated persona (`personas/archivist.md`, sonnet) whose
sole job is to keep the card base correct and current. It is **not** in the
chat/dispatch path — it does no reviewing or coding and posts no comments.

**Trigger.** Every new comment is a chance for the knowledge base to drift, so
the archivist reviews comments. `archivist_handler` (a third stage of the chat
cycle, gated by `ENABLE_ARCHIVIST`) sweeps
`GET /api/internal/comments?needs_archival=true` — comments with no
`archivist-reviewed` prop — oldest-first, capped at `ARCHIVIST_BATCH` per cycle.
For each it creates a sweep WorkItem (`target_persona=archivist`,
`triggering_comment_id=NULL`) and marks the comment reviewed. Dispatch reuses
`work_item_handler` + the always-on fixer pass.

**Cutoff, not backlog.** Migration `010` marks all pre-existing comments
reviewed, so the archivist only processes comments created from its
introduction forward. On a fresh DB this is a no-op — a new install archives
from its first comment.

**What it does.** Reads the full task context, searches existing cards, then
does exactly one of: **create** a card, **update** one, or **nothing** (the
common, correct default). Cards it touches are tagged `archivist`.

**References.** Every card it writes cites its provenance inline — source task
id + comment id(s) — and cross-links related cards by slug. The shared fragment
tells reading personas to follow those references (`get_task`,
`get_task_comments`, `wp knowledge show <slug>`) when they need the full story.

**Silent + audited.** Its real output is the card changes; `work_item_handler`
suppresses the reply comment for archivist items but still persists the output
on the WorkItem for audit.

> Note: cards land as `is_valid=true` immediately — there is no candidate/review
> gate. The archivist is trusted to curate conservatively (search-first,
> bias-to-nothing). A `candidate → promote` gate is the obvious lever if
> auto-authored noise ever becomes a problem.

## Authoring

Knowledge is un-externalized, not missing — it lives in code, git history,
and your head. Authoring is a **sit-down session** (~1-2 hrs) using
`wp knowledge add`: pick a topic, write the card, tag it, save. Later, an
AI-assisted code-mining flow can draft `candidate` cards from the repos for
human review — but that's a future phase, not v1.

## Surfaces

- **Backend API** (Go, owns Postgres) — the endpoints above.
- **CLI**: `wp knowledge add|list|show|search|edit|rm`.
- **Poller**: a `search_knowledge_cards` API-client method + a prompt-
  injection step in the dispatch path.

## Out of scope (future)

- User-facing JWT read endpoints + web UI search.
- Pre-dispatch injection token-budget tuning.
- A candidate/review gate for archivist-authored cards (cards are live
  immediately today; add the gate only if auto-authored noise warrants it).
- Code-mining extraction flow (one-shot bulk draft from the repos — distinct
  from the archivist's per-comment upkeep).
- `pgvector` semantic retrieval — only if corpus outgrows FTS+context.
- Card structure (types, lifecycle) — only if a real need forces it.
