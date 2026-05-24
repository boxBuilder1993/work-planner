# Knowledge base (ChromaDB)

You have access to a per-user vector knowledge base via two MCP tools:

- `mcp__workplanner__query_knowledge` — semantic search over past entries.
- `mcp__workplanner__store_knowledge` — write a new entry.

## When to query

- **Before proposing something non-trivial.** "Has this been discussed/decided
  already?" — e.g. before suggesting an auth approach, query for
  `"auth approach"` or `"JWT decision"`.
- **When stuck.** Query for the failure mode you're hitting.
- **When the task references something unfamiliar.** Query first to see if
  past work covered it.

Don't over-query. 1-3 queries per turn is plenty. If the first few queries
return nothing relevant, the KB doesn't have an answer — move on.

## When to store

Store entries that **future you (or another persona) would benefit from**.
Concrete examples:

- A decision made in this task ("Chose python-jose because pyjwt lacked
  JWE; reconsider if encryption requirements change").
- A pattern discovered ("API handlers use FastAPI + Pydantic, see
  `backend/api/routes/`").
- A failure ("Tried SQLite for sessions, too slow under load — switched
  to Redis").
- Implementation notes that survive the immediate task.

Don't store:

- Things obvious from the code or one `grep` away.
- The current task description (it's already in the task DB).
- Status updates ("done", "in progress").

## `work_type` values

When calling `store_knowledge`, pick one:

| `work_type` | For |
|---|---|
| `requirements_spec` | What the task is trying to achieve, in distilled form |
| `adr` | An architecture decision — what / why / alternatives considered |
| `plan` | A decomposition or roadmap that took thought |
| `implementation_note` | "How we did X" — patterns, gotchas, conventions |
| `review_feedback` | Critique that should inform future work |
| `delivery_report` | What shipped, what's left, links to PRs |
| `clarification` | A user-given answer that matters beyond the moment |
| `debug_note` | "Bug X was caused by Y; symptom is Z" |

## Tags

Pass `tags` as a list of free-form strings. Useful tags: project name,
tech stack, feature area. Keep tags short (1-3 words each), 2-5 tags
per entry.
