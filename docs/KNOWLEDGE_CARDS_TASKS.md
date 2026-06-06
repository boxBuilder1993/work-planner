# Knowledge Cards — Task List

Phased implementation of [KNOWLEDGE_CARDS_DESIGN.md](KNOWLEDGE_CARDS_DESIGN.md).
Build order: storage backend → CLI (authoring) → sit-down population →
persona consumption.

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done

---

## Phase A — Backend storage + retrieval

The `knowledge_cards` table, CRUD, and Postgres FTS. No ChromaDB.

- [ ] **A1. Migration `008_knowledge_cards`** (up + down)
  - Table per the design schema (slug PK, lifecycle CHECKs, arrays).
  - Indexes: `(type,status)`, `(authority,status)`, GIN on `tags`, GIN on
    the `to_tsvector('english', title||question||answer||body)` expression.
- [ ] **A2. `model.KnowledgeCard`** + request types
  - `KnowledgeCard` struct (camelJSON tags).
  - `CreateKnowledgeCardRequest`, `UpdateKnowledgeCardRequest`.
- [ ] **A3. Store methods** (`store.go`)
  - `CreateKnowledgeCard` (reject duplicate slug with clear error).
  - `GetKnowledgeCard(id)`.
  - `ListKnowledgeCards(type, status, authority, tags)`.
  - `SearchKnowledgeCards(q, type, tags, authority, includeSuperseded)` —
    `plainto_tsquery` + `ts_rank`, default excludes superseded/archived,
    authority-weighted ordering (canonical > reviewed > candidate).
  - `UpdateKnowledgeCard` (partial; supports status/authority transitions,
    supersedes/superseded_by linking, field edits).
- [ ] **A4. Handlers + routes** (`internal.go`)
  - Create / List / Get / Search / Update handlers.
  - Route cases (search before `/:id`, like the work-items ordering).
- [ ] **A5. Register routes** (`main.go`)
  - `/api/internal/knowledge-cards` and `/api/internal/knowledge-cards/`.
- [ ] **A6. Smoke test** via curl against localdev: create → list → get →
  search (keyword hit + miss) → supersede → verify excluded from default
  search.
- [ ] **A7. Commit + push.**

## Phase B — `wp knowledge` CLI

Authoring surface for the sit-down + engineer's active query via shell.

- [ ] **B1. API client methods** (`cli/.../api.py`)
  - `create_knowledge_card`, `get_knowledge_card`, `list_knowledge_cards`,
    `search_knowledge_cards`, `update_knowledge_card`.
- [ ] **B2. Render helpers** (`cli/.../render.py`)
  - `knowledge_card_table`, `knowledge_card_detail` (frontmatter + answer +
    body + lifecycle + related).
- [ ] **B3. CLI commands** (`cli/.../cli.py`) — `wp knowledge` group:
  - `add` — interactive prompts (id/type/title/question/answer/body/tags),
    or flags for scripted use. Defaults authority=candidate unless
    `--canonical`.
  - `list [--type --status --authority --tag]`
  - `show <id>`
  - `search <query> [--type --tag]`
  - `edit <id> [--field ...]`
  - `promote <id>` — authority → canonical.
  - `supersede <old-id> <new-id>` — link + flip old to superseded.
- [ ] **B4. README** — command table + the card-authoring workflow.
- [ ] **B5. Smoke test**: `wp knowledge add` a real card, list/show/search it.
- [ ] **B6. Commit + push.**

## Sit-down — populate the corpus

Not code. ~1-2 hour interactive session using `wp knowledge add`.

- [ ] **S1. Seed the highest-value cards**: tech stack, repo layout, commit/
  branch conventions, the WorkPlanner architecture, the meal-planner domain
  rules, the AI-orchestration model (personas/work-items/proxy).
- [ ] **S2. Tag + set authority=canonical** on the verified ones.

## Phase C — Pre-dispatch injection

Surface cards to personas. Build after cards exist (post sit-down).

- [ ] **C1. Poller API-client method** (`ai-poller/api_client.py`)
  - `search_knowledge_cards(query, tags, type, limit)`.
- [ ] **C2. Injection in the dispatch path**
  - In prompt-building (chat_prompt / chat_handler): fetch task-relevant
    cards (by tags/keyword from task title+description), render an injected
    `<knowledge>` block, prepend to the persona context. Order stable-first
    for cache-friendliness.
  - Cap the injected set (token budget) — top-N by rank; log what was
    dropped.
- [ ] **C3. Persona prompt note** — a shared fragment telling personas how to
  read injected cards (canonical = trusted, candidate = verify; cards
  orient, live code/systems are truth) and that engineer can
  `wp knowledge search` for more.
- [ ] **C4. Tests** (poller-side rendering/selection logic).
- [ ] **C5. Commit + push.**

## Future (not scheduled)

- [ ] Code-mining extraction flow (AI drafts `system`/`convention`
  candidates from repos).
- [ ] `pgvector` semantic retrieval — when corpus outgrows cached context.
- [ ] Auto repo-map generation for engineer orientation.
- [ ] Staleness sweep (`last_verified` aging → flag for re-verification).
