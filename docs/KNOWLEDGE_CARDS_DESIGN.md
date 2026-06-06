# Knowledge Cards

A curated, retrievable company knowledge base for the AI personas. Each
**card** answers one question an agent will actually ask. Cards are the
unit of company context — authored by humans (and AI-assisted extraction),
stored durably, and surfaced to personas at dispatch time.

This doc is the design. The phased work-list lives in
[KNOWLEDGE_CARDS_TASKS.md](KNOWLEDGE_CARDS_TASKS.md).

## Why cards, not a wiki / vector dump

Retrieval is question-driven. An agent doesn't browse — it asks "how does
our auth work?" and needs a self-contained answer back. So the unit of
knowledge is **"an answer to a question someone will ask,"** not "a
document about a topic." That single reframe fixes the format: small,
atomic, front-loaded, one concept each.

## What we are NOT building (and why)

- **No vector store / ChromaDB for v1.** The corpus is bounded and
  hand-authored (dozens→low-hundreds of cards). It fits in context. For
  bounded corpora, Postgres full-text search + tag filtering + cached
  context injection beats a vector pipeline on fidelity *and* complexity.
  Add `pgvector` only if/when the corpus outgrows a cached context budget.
- **No new MCP tool.** Office infosec gates new MCP tools. Personas consume
  knowledge via (1) pre-dispatch injection by the poller over plain HTTP,
  and (2) the existing shell capability calling `wp knowledge search`.
  Neither adds a reviewable tool surface.
- **No raw-code caching.** Code is volatile (agents edit it live) and large.
  Agents navigate code on demand (grep/read) — always current, strictly
  better than a stale index. We cache *understanding* of the code
  (`system` + `convention` cards), not the code itself.

## The card

Source of truth is a Postgres row. Authored/edited as the logical
equivalent of this markdown shape:

```markdown
---
id: auth-jwt-flow                    # stable slug; used for cross-linking
type: system                         # system|decision|runbook|convention|glossary|postmortem
title: How JWT authentication works
question: How does our auth / login / token validation work?
tags: [auth, jwt, security, backend]
applies_to: [backend, api]
authority: canonical                 # candidate|reviewed|canonical
status: active                       # active|superseded|stale|archived
last_verified: 2026-06-03
related: [auth-decision-jwt-over-sessions]
---

**Answer (read this first).** Auth is JWT-based. Tokens issue on login at
`/api/auth/google`, carry 30-day expiry, validated in `middleware/auth.go`
on every protected route. No server-side sessions.

## Details
...
```

### Card types (defined by the question shape)

| Question shape | type | Example |
| --- | --- | --- |
| "How does X work?" | `system` | How does the dispatch pipeline flow? |
| "Why did we decide X?" | `decision` | Why JWT over sessions? |
| "How do I do X?" | `runbook` | How to deploy a hotfix |
| "What's our convention for X?" | `convention` | Commit message format |
| "What does X mean?" | `glossary` | What is a "work item" |
| "What broke and why?" | `postmortem` | The 901-task duplication incident |

### Fields doing the heavy lifting

- **`question`** — embedded into FTS alongside the answer. A query like
  "how do I log in" matches a card whose body never says "log in." Forces
  the author to know what they're answering; no question → no card.
- **`answer`** — front-loaded TL;DR, self-contained. The chunk most likely
  surfaced; must stand alone.
- **`authority`** defaults to `candidate` — agent-written cards and first
  drafts are provisional until a human promotes them to `canonical`. This
  is the pollution firewall: agents read canonical as trusted, candidates
  as "verify before relying."
- **`status` + `supersedes`/`superseded_by`** — lifecycle. Retrieval
  excludes `superseded`/`archived` by default. A new decision marks the old
  one superseded rather than deleting it (audit trail).
- **`last_verified`** — staleness signal. Cards describe the world as of
  this date; personas are told to verify specifics against live code/systems
  when correctness matters.

## Storage

- **Source of truth: `knowledge_cards` table (Postgres).** Rows are
  editable, listable, transactional, durable. Mirrors the WorkItems pattern.
- **Retrieval: Postgres full-text search** over `title || question ||
  answer || body`, plus tag/type/authority/status filtering. GIN indexes on
  the tsvector expression and on `tags`.
- **Slug `id`** (not UUID) — human-readable, good for `related` cross-links
  and for referencing during authoring.

## Trust division (cards vs ground truth)

- **Cards = the mental model.** Fast orientation, possibly slightly stale.
- **Live code / systems = ground truth.** When correctness matters, the
  agent verifies against the real thing.

Personas are told explicitly: *"system cards describe the code as of their
`last_verified` date — orient with them, but the actual code is truth;
verify specifics against it."* Stops stale cards from causing
confident-but-wrong work.

## Consumption (no MCP)

1. **Pre-dispatch injection (primary).** When the poller builds a dispatch
   prompt, it queries the knowledge backend (plain HTTP, like it already
   does for tasks/comments) for cards relevant to the task — filtered by the
   task's tags/type and/or a keyword pass — and injects the matched cards
   into the prompt. Works for *every* persona regardless of tools (manager
   and planner have no shell). Order the injected block by stability so it
   caches well: conventions/architecture first (cached prefix), task-
   relevant cards next.

2. **Active query via CLI (shell-capable personas).** The engineer (which
   already has Bash/run_command) runs `wp knowledge search "..."` for deeper
   lookups mid-task. No new tool surface — it's the existing shell calling a
   CLI binary that hits the HTTP API.

## Authoring

Humans don't write a wiki cold. The knowledge is un-externalized, not
missing — it lives in code, git history, and your head. Authoring is
AI-assisted:

- **Sit-down session** using `wp knowledge add` — interactive: pick a topic
  gap, answer a few sharp questions, a card is drafted in the canonical
  format, you review and save. ~1-2 hours bootstraps a useful corpus.
- **Code-mining (later)** — an extraction flow reads the repos and drafts
  `system`/`convention` cards as `candidate`, queued for human promotion.

## Surfaces

- **Backend API** (Go, owns Postgres):
  - `POST /api/internal/knowledge-cards` — create
  - `GET /api/internal/knowledge-cards` — list/filter (type, status,
    authority, tags)
  - `GET /api/internal/knowledge-cards/:id` — fetch one
  - `PATCH /api/internal/knowledge-cards/:id` — edit / supersede / promote
  - `GET /api/internal/knowledge-cards/search?q=&type=&tags=&authority=` —
    FTS retrieval, authority-weighted, superseded-excluded
- **CLI**: `wp knowledge add|list|show|edit|promote|supersede|search`
- **Poller**: a `search_knowledge_cards` API-client method + a prompt-
  injection step in the dispatch path.

## Out of scope (future)

- Vector search (`pgvector`) — only when corpus outgrows cached context.
- Auto repo-map generation — when engineer orientation is the bottleneck.
- Code-mining extraction flow — after the manual bootstrap proves the format.
- Staleness sweeps / scheduled re-verification.
