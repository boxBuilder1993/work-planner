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

## Consumption (no MCP)

1. **Pre-dispatch injection (primary, all personas).** When the poller
   builds a dispatch prompt, it searches the knowledge backend (plain HTTP,
   like it already fetches tasks/comments) for cards relevant to the task —
   by the task's tags and/or a keyword pass over its title+description — and
   injects the matched cards into the prompt. Works for every persona,
   including shell-less manager/planner. Token-budgeted (top-N).

2. **Active query via CLI (shell-capable personas).** The engineer runs
   `wp knowledge search "..."` through its existing Bash capability for
   deeper lookups mid-task. No new tool surface.

Personas are told: cards orient you, but live code/systems are ground
truth — verify specifics against them when correctness matters.

## Write access

Create / edit / delete are **human-only via `wp knowledge`** in v1.
Personas do not write cards (no pollution risk, format still proving out).
A persona that discovers something worth recording says so in its reply; a
human adds the card. **Manager-write** is a plausible future (manager is the
orchestrator) but needs either shell access or an infosec-reviewed tool —
deferred.

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
- Agent-proposed cards / manager-write.
- Code-mining extraction flow.
- `pgvector` semantic retrieval — only if corpus outgrows FTS+context.
- Card structure (types, lifecycle) — only if a real need forces it.
