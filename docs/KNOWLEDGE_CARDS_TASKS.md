# Knowledge Cards — Task List

Phased implementation of [KNOWLEDGE_CARDS_DESIGN.md](KNOWLEDGE_CARDS_DESIGN.md).
Build order: storage backend → CLI (authoring) → sit-down population →
persona consumption.

Status: `[ ]` todo · `[~]` in progress · `[x]` done

---

## Phase A — Backend storage + retrieval  ✅ DONE

Minimal `knowledge_cards` table, CRUD, Postgres FTS. No ChromaDB.

- [x] **A1. Migration `008_knowledge_cards`** (up + down)
- [x] **A2. `model.KnowledgeCard`** + create/update request types
- [x] **A3. Store methods** — Create/Get/List/Search/Update/Delete +
  scanKnowledgeCards. FTS via `plainto_tsquery` + `ts_rank`; invalid
  excluded by default.
- [x] **A4. Handlers + routes** (`internal.go`) — slug validation, 409 on
  dup, search before `/:id`.
- [x] **A5. Register routes** (`main.go`).
- [x] **A6. Smoke test** — all paths verified: create/dup-409/bad-slug-400,
  list, search (keyword/multiword/tag/miss), validity exclude+include,
  delete. ✅
- [x] **A7. Commit + push.**
- [x] **A8. Committed integration tests** (`backend/tests/integration/`,
  `//go:build integration`) — black-box HTTP against an isolated e2e stack
  (`docker-compose.test.yml`: ephemeral Postgres + backend, ports 5433/8081).
  `make test-e2e-up|down`, `make test-integration`, `make test-e2e` (one-shot).
  New `integration` job in `.github/workflows/test.yml` runs on PRs. 6/6
  subtests pass. ✅

## Phase B — `wp knowledge` CLI

Authoring surface for the sit-down + engineer's active query via shell.

- [ ] **B1. API client methods** (`cli/.../api.py`): create/get/list/search/
  update/delete knowledge cards.
- [ ] **B2. Render helpers** (`cli/.../render.py`): card table + detail.
- [ ] **B3. `wp knowledge` command group** (`cli/.../cli.py`):
  - `add <id> [-c content | stdin | @file] [--tag ...]`
  - `list [--tag ...] [--all]`
  - `show <id>`
  - `search "<phrase>" [--tag ...] [--all]`
  - `edit <id> [-c content | --tag ... | --valid/--invalid]`
  - `rm <id>`
- [ ] **B4. README** — command table + authoring workflow.
- [ ] **B5. Smoke test** against prod: add a real card, list/show/search.
- [ ] **B6. Commit + push.**

## Sit-down — populate the corpus

Interactive ~1-2 hr session with `wp knowledge add`. Not code.

- [ ] **S1. Seed high-value cards**: tech stack, repo layout, commit/branch
  conventions, WorkPlanner architecture, meal-planner domain rules, the
  AI-orchestration model (personas / work-items / proxy / fixer).
- [ ] **S2. Tag them well** (so injection + search land).

## Phase C — Pre-dispatch injection

Surface cards to personas. Build after cards exist.

- [ ] **C1. Poller API-client method** (`ai-poller/api_client.py`):
  `search_knowledge_cards(query, tags, limit)`.
- [ ] **C2. Injection in the dispatch path** — fetch task-relevant cards
  (tags + keyword from task title/description), render a `<knowledge>`
  block, prepend to the persona context. Top-N by rank; log drops.
- [ ] **C3. Shared persona fragment** — how to read injected cards (orient
  with them; live code/systems are truth) + engineer can
  `wp knowledge search` for more.
- [ ] **C4. Tests** (selection/rendering).
- [ ] **C5. Commit + push.**

## Future (not scheduled)

- [ ] User-facing JWT read endpoints + web UI search.
- [ ] Manager-write (needs shell or infosec-reviewed tool).
- [ ] Code-mining extraction flow (AI drafts candidate cards from repos).
- [ ] `pgvector` semantic retrieval — if corpus outgrows FTS + context.
- [ ] Card structure (types / lifecycle) — only if a real need forces it.
