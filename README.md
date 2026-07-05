# WorkPlanner

**A task-and-project planning tool for engineering managers.** Break work into a
tree of tasks, give them estimates, assignees, and dependencies, and get a
**portfolio-wide schedule** with accurate ETAs computed against your team's shared
capacity. AI assistance is an optional add-on — the core is a faithful planning
calculator, not a predictor.

> **Primary use case:** an EM planning several projects across shared people, who
> needs to give bosses accurate delivery dates. Accurate ETAs require scheduling
> *all* projects together against each person's real hours — which is exactly what
> the engine does.

---

## What it does

- **Projects & plans** — a "project" is just a top-level task. Every task can be
  broken down into an infinitely-nested tree (WBS). Set estimate (hours),
  assignee, priority, buffer, dependencies, and due date per task.
- **Portfolio-wide scheduling** — one scheduling pass over *all* your tasks. A
  person shared across projects is serialized across the whole portfolio, so ETAs
  reflect real contention for shared capacity.
- **Schedule view** — an assignee × date grid with hour-level task blocks,
  critical-path highlighting, weekends/holidays/time-off, and CSV export.
- **Team & calendar** — people (hours/day), per-person time off, company
  holidays, and weekend definition — all inputs the engine honors.
- **AI add-on** *(optional)* — an AI poller can act on `@ai` mentions to help
  break down and action work. Not required for the core planning workflow.

---

## Architecture

| Component | Stack | Role |
|---|---|---|
| `backend/` | Go, Postgres | REST API, auth (JWT), and the scheduling engine |
| `web/` | React 19, Vite, TypeScript, Tailwind v4, shadcn/ui | The web app (monochrome SaaS UI) |
| `cli/` | Python (`wp`) | Command-line client for tasks/planner/knowledge |
| `ai-poller/` | Python, LiteLLM / Claude Agent SDK | Optional AI personas that act on `@ai` mentions |
| `claude-proxy/` | Python | Local proxy that runs Claude via your subscription |
| `app/` | Kotlin (Android) | Mobile client (not under active development) |

Data lives in **Postgres** (tasks, people, calendar, dependencies, knowledge
cards). There is no separate vector store — the knowledge base is Postgres
full-text search (ChromaDB was removed in favor of this; see below).

---

## The scheduling engine

Pure Go, no I/O, fully unit-tested (`backend/internal/planner/`). One pass over
all of a user's non-closed tasks:

1. **Cycle check** — topological sort of leaf dependencies.
2. **Priority-driven, resource-constrained placement** — among tasks whose
   dependencies are resolved, the most important (lowest priority value, then
   manual position) grabs its assignee's next free slot.
3. **Hour-native packing** — each person has an `(day, hoursUsed)` clock; tasks
   pack intra-day (two 4h tasks share one 8h day), spill across days, and skip
   weekends, company holidays, and that person's time off.
4. **Dependencies** — finish-to-start at day granularity.
5. **Rollup** — each parent's start/end spans its children, plus its buffer.
6. **Critical path** — dependency-based backward trace from the makespan.

Design + rationale: [docs/PLANNER_DESIGN.md](docs/PLANNER_DESIGN.md). Known
limitation: the critical path is dependency-based, not resource-aware (a
resource-aware "critical chain" is a future upgrade).

---

## Running locally (Docker)

Everything runs on your machine — no Railway, no tunnel.

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- (Only for the AI add-on) [Claude Code CLI](https://claude.ai/code), logged in

### 1. Configure environment
```bash
cp .env.example .env
```
Set in `.env`:
```
JWT_SECRET=<long random string>        # openssl rand -hex 32
INTERNAL_API_KEY=<long random string>
```

### 2. Start everything
```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| Backend API | http://localhost:8080 |

### 3. Sign in
Open http://localhost:3000 and enter your email + name — local email auth, no
Google account needed.

### Stopping
```bash
docker compose down       # stop, keep data
docker compose down -v    # stop and wipe data
```

### Front-end dev loop (hot reload)
```bash
cd web && npm install && npm run dev    # http://localhost:5173, talks to :8080
```

---

## AI configuration (optional add-on)

The AI poller uses LiteLLM, so it works with Claude (cloud), a local Ollama
model, or any LiteLLM provider. It is **not needed** for planning.

```bash
make ai-claude    # use Claude via Anthropic (set ANTHROPIC_API_KEY in ai-poller/.env)
make ai-ollama    # use a local model (pulls qwen2.5:14b)
```

Key env vars (in `ai-poller/.env`):

| Var | Claude | Ollama |
|---|---|---|
| `AI_MODEL` | `claude-haiku-4-5` | `ollama/qwen2.5:14b` |
| `AI_API_BASE` | *(empty)* | `http://localhost:11434` |
| `AI_API_KEY` | your key | *(empty)* |

For a Claude *subscription* (no API key), run the local proxy first:
`cd claude-proxy && ./start.sh` (listens on `:8400`; the poller reaches it at
`host.docker.internal:8400`). Change `AI_MODEL` in Railway to switch models in
production without redeploying.

---

## Deployment (Railway)

Auto-deploys from `main`. Production services: **backend**, **frontend**,
**ai-poller**, **Postgres**. (The former **chromadb** service was removed once the
knowledge base moved to Postgres — see #48.)

---

## Testing

```bash
make test-backend      # Go unit tests (incl. the scheduling engine)
make test-e2e          # HTTP integration suite against an isolated test stack
cd web && npm run lint && npm run build
```

---

## Docs

- [docs/PLANNER_DESIGN.md](docs/PLANNER_DESIGN.md) — scheduling model & engine
- [docs/PLANNER_IMPLEMENTATION.md](docs/PLANNER_IMPLEMENTATION.md) — build notes
- [docs/KNOWLEDGE_CARDS_DESIGN.md](docs/KNOWLEDGE_CARDS_DESIGN.md) — knowledge base (Postgres, no vector store)
- [docs/CHAT_DESIGN.md](docs/CHAT_DESIGN.md) · [docs/DRIVER_DESIGN.md](docs/DRIVER_DESIGN.md) · [docs/WORK_ITEMS_DESIGN.md](docs/WORK_ITEMS_DESIGN.md) — AI subsystem

---

## Project status

- **Scheduling engine** — done; hour-native packing + priority-driven contention
  + dependencies + critical path; unit-tested, portfolio-wide.
- **Web app** — redesigned (monochrome shadcn). Screens: Projects (home),
  Project (Plan + Schedule tabs, recursive to any depth), Team & Calendar,
  Search, Knowledge, Settings. Task editing: description (markdown), comments,
  properties (assignee/due/estimate/priority/buffer/dependencies), status.
- **CLI (`wp`)** — tasks, planner fields, knowledge.
- **AI poller** — functional add-on (personas act on `@ai` mentions).
- **Android** — exists, not under active development.
