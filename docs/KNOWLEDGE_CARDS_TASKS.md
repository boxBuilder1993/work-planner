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

## Phase B — `wp knowledge` CLI  ✅ DONE (PR)

Authoring surface for the sit-down + engineer's active query via shell.

- [x] **B1. API client methods** (`cli/.../api.py`): create/get/list/search/
  update/delete knowledge cards.
- [x] **B2. Render helpers** (`cli/.../render.py`): card table + detail.
- [x] **B3. `wp knowledge` command group** — add/list/show/search/edit/rm.
  `add`/`edit` content from `-c`, `@file`, or stdin; slug validation.
- [x] **B4. README** — command table + authoring workflow.
- [x] **B5. Tests** — `cli/tests/test_knowledge.py` (14 unittest + CliRunner,
  mocked Client). Wired into `make test-cli` + a new `cli` CI job. Also
  manually verified end-to-end against localdev. ✅
- [x] **B6. Branch + PR** (per the new branch/PR/CI-green norm).

## Sit-down — populate the corpus

Interactive ~1-2 hr session with `wp knowledge add`. Not code.

- [ ] **S1. Seed high-value cards**: tech stack, repo layout, commit/branch
  conventions, WorkPlanner architecture, meal-planner domain rules, the
  AI-orchestration model (personas / work-items / proxy / fixer).
- [ ] **S2. Tag them well** (so injection + search land).

## Phase C — Agentic knowledge pull  ✅ BUILT (C6 verify pending cards)

Personas search + read cards themselves via `wp knowledge` as a required
due-diligence step. No injection, no MCP. Branch `feat/knowledge-due-diligence`.

- [x] **C1. `wp` reachable in the dispatch environment** — proxy
  `_claude_subprocess_env()` exports `WP_BASE_URL` / `WP_INTERNAL_KEY` (from
  `WORKPLANNER_API_URL` / `INTERNAL_API_KEY`) into the `claude -p` subprocess.
  `wp` install documented in the proxy README. Proxy tests (3) cover it.
- [x] **C2. Shell path for every persona** — engineer + reviewer already have
  `mcp__workplanner__run_command`; manager / planner / default got
  `Bash(wp knowledge:*)` (the scopable grant — `run_command` is unrestricted).
  persona test asserts every persona has run_command OR scoped Bash.
  **⚠️ C6 must verify** the `Bash(wp knowledge:*)` pattern actually gates
  under `--allowedTools` + `--dangerously-skip-permissions`. If it doesn't
  scope, manager/planner/default get full Bash — decide then.
- [x] **C3. Shared fragment** `_shared/knowledge_cards.md`, included in all
  five personas: first-action mandate, cost framing, conflict rule, mention
  cards used, cards-orient-but-verify. No verification/gate (trust the prompt).
- [x] **C3b. Fixer on the rest** — planner / reviewer / default given
  `fixer_model` (engineer + manager already had it); `output_format.md`
  dropped from their includes. All five now reply naturally.
- [x] **C4. `max_turns` → 40** for manager / planner / reviewer / default
  (engineer stays 100). All persona `version`s bumped.
- [x] **C5. Tests** — proxy `ClaudeSubprocessEnvTests` (3) + poller
  `RealPersonaKnowledgeCardsTest` (4: fragment / fixer / shell-path /
  max_turns). proxy 20/20, poller 95/95.
- [ ] **C6. Manual verify** (after sit-down) — dispatch a real mention;
  confirm the persona runs `wp knowledge search`, uses a card, and that the
  scoped Bash genuinely restricts manager/planner/default.
- [x] **C7. Branch + PR + CI green + merge.** *(PR open; merge after green)*

### Phase C — optional fast-follow

- [ ] **Card catalog injection** — poller injects `id` + `tags` + one-line
  per card (lightweight, cacheable) so personas know what exists and can
  pull the rest. Only if pure-pull recall proves weak. (A recall aid, not a
  verification.)

## Future (not scheduled)

- [ ] User-facing JWT read endpoints + web UI search.
- [ ] Manager-write (needs shell or infosec-reviewed tool).
- [ ] Code-mining extraction flow (AI drafts candidate cards from repos).
- [ ] `pgvector` semantic retrieval — if corpus outgrows FTS + context.
- [ ] Card structure (types / lifecycle) — only if a real need forces it.
