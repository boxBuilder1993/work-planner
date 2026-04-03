# Company v1 Algorithm — Spec

## Philosophy

Model a software company. You are the CEO. You send requests, the company delivers.
The company clarifies before building, debates architecture, reviews everything heavily.

**Priorities**: Clarification > Quality > Speed

---

## Roles

| Role | Count | Responsibility | Talks to |
|------|-------|---------------|----------|
| **Director** | 1 | Interviews CEO, owns requirements, final delivery | CEO (you) |
| **Architect A** | 1 | Proposes approach, critiques B, refines | Director |
| **Architect B** | 1 | Proposes approach, critiques A, refines | Director |
| **Manager** | 1 | Plans work, coordinates engineers, merges PRs | Director |
| **Engineer** | N | Implements, opens PRs | Manager |
| **Reviewer** | 1 per PR | Reviews code quality, tests, correctness | Manager |

---

## Configuration

Stored in `props`:

```json
{
  "algorithm": "company_v1",
  "config": {
    "debate_rounds": 3,
    "auto_approve_architecture": false
  }
}
```

- `debate_rounds`: Number of architect debate rounds (default 3, min 1, max 5)
- `auto_approve_architecture`: If true, Director approves architecture without asking CEO

---

## Phases

### Phase 1: CLARIFICATION

**Owner**: Director
**State**: `clarifying`

Director reads the request and posts clarifying questions to the CEO as proposals.
One question at a time. CEO answers (comments) or says "just decide."

The Director keeps asking until confident it understands:
- What to build
- What NOT to build (non-goals)
- Success criteria
- Constraints (tech stack, timeline, etc.)

When satisfied, Director writes a **requirements spec** and posts it as a proposal.

**State**: `spec_proposed`

CEO approves → Phase 2. CEO denies with feedback → Director revises.

---

### Phase 2: ARCHITECTURE (Dual-Architect Debate)

**Owner**: Director (orchestrates)
**Participants**: Architect A, Architect B

The Director creates two subtasks: `Architect A` and `Architect B`.

#### Round structure (repeats `debate_rounds` times)

**Round N (odd) — Propose/Revise**:
- Architect A posts a proposal (or revision) on its own task
- Architect B posts a proposal (or revision) on its own task
- Both run in parallel

**Round N (even) — Critique**:
- Architect A reads B's latest proposal → posts critique + what to steal
- Architect B reads A's latest proposal → posts critique + what to steal
- Both run in parallel

After the first round, every proposal must reference the other architect's work:
- "I agree with B's suggestion on X"
- "I disagree with B's approach to Y because..."
- "I'm incorporating B's idea about Z"

#### Final round — Position statements

After all debate rounds:
- Architect A posts final recommendation with explicit agree/disagree list
- Architect B posts final recommendation with explicit agree/disagree list

#### Synthesis

Director reads all debate comments from both architects.
Director writes an **Architecture Decision Record (ADR)**:
- Decision
- Alternatives considered (from both architects)
- Why this approach won (synthesized from the debate)
- Risks acknowledged
- Posts as proposal

**State**: `arch_proposed`

CEO approves (or auto-approve if configured) → Phase 3.

---

### Phase 3: PLANNING

**Owner**: Manager
**State**: `planning`

Manager reads:
- Requirements spec (from Phase 1)
- ADR (from Phase 2)

Manager creates subtasks with:
- Clear title and description
- Acceptance criteria (what "done" looks like)
- Dependencies noted

Manager posts the plan as a proposal on its own task.
Director reviews the plan for completeness against the spec.
Architect A or B reviews for technical soundness.

**State**: `plan_proposed` → approved → `plan_approved`

Manager creates the actual subtasks → `implementing`

---

### Phase 4: IMPLEMENTATION

**Owner**: Manager (coordinates)
**State**: `implementing`

Each Engineer subtask follows:

```
propose_work → (Manager approves) → implement → open PR →
  → Reviewer reviews PR →
    → approved → Manager merges
    → rejected → Engineer fixes → Reviewer re-reviews
```

Engineers work in parallel where dependencies allow.
Manager tracks progress and unblocks engineers.

**Reviewer for each PR**:
- Different agent than the one that wrote the code
- Checks: code quality, test coverage, matches acceptance criteria, no obvious bugs
- Must approve before Manager can merge

---

### Phase 5: INTEGRATION REVIEW

**Owner**: Manager + Architect
**State**: `integration_review`

After all PRs are merged:

1. Manager verifies:
   - All subtasks closed
   - All tests pass
   - No merge conflicts

2. Architect (A or B, Director picks) reviews the complete codebase:
   - Does the implementation match the ADR?
   - Are there architectural violations?
   - Is the code cohesive across PRs?
   - Any missing pieces?

3. If gaps found:
   - New subtasks created → back to `implementing`

4. If all good:
   - Manager posts completion report → Director

**State**: `review_complete`

---

### Phase 6: DELIVERY

**Owner**: Director
**State**: `delivering`

Director writes a delivery report:
- Original request (what CEO asked for)
- Requirements spec (what was clarified)
- Architecture decision (what was debated)
- What was built (list of PRs, files, features)
- Requirement → deliverable mapping (every requirement traced to code)
- What was NOT built (explicit non-goals confirmed)

Director posts as proposal on the top-level task.

**State**: `delivered`

CEO reviews and closes.

---

## States (12)

| State | Owner | What's happening |
|-------|-------|-----------------|
| `clarifying` | Director | Asking CEO questions |
| `spec_proposed` | Director | Spec posted, waiting for CEO approval |
| `architecting` | Director | Dual-architect debate in progress |
| `arch_proposed` | Director | ADR posted, waiting for approval |
| `planning` | Manager | Breaking work into tasks |
| `plan_proposed` | Manager | Plan posted, waiting for approval |
| `implementing` | Manager | Engineers working, PRs being reviewed |
| `integration_review` | Architect | Holistic review of all merged work |
| `review_complete` | Manager | Reported to Director |
| `delivering` | Director | Writing delivery report |
| `delivered` | Director | Report posted, waiting for CEO to close |
| `awaiting_input` | Any | Question escalated, waiting for answer |

---

## Escalation

```
Engineer stuck → Manager
  Manager can answer → responds via deny_child_proposal with feedback
  Manager can't answer → escalates to Director

Manager stuck → Director
  Director can answer → responds
  Director can't answer → asks CEO

CEO is only bothered when:
  1. Clarifying questions (Phase 1)
  2. Spec approval (Phase 1)
  3. Architecture approval (Phase 2, if not auto-approve)
  4. Delivery acceptance (Phase 6)
  5. Genuine blockers escalated from Director
```

---

## Task tree structure

```
[Your request] (algorithm: company_v1)
  ├── [Architect A] (role: architect)
  ├── [Architect B] (role: architect)
  ├── [Subtask 1] (role: engineer)
  │     └── [Review: Subtask 1] (role: reviewer)
  ├── [Subtask 2] (role: engineer)
  │     └── [Review: Subtask 2] (role: reviewer)
  ├── [Subtask 3] (role: engineer)
  │     └── [Review: Subtask 3] (role: reviewer)
  └── [Integration Review] (role: architect)
```

All are children of the top-level task. The Manager is the top-level task's agent.
The Director is also the top-level task's agent (different phases).

---

## Debate round detail

For `debate_rounds = 3`:

```
Round 1 (parallel):
  A proposes: "I suggest using Flask with SQLite because..."
  B proposes: "I suggest using FastAPI with JSON files because..."

Round 2 (parallel, after reading each other):
  A critiques B: "JSON files won't scale, but I like FastAPI's async. Revised: FastAPI + SQLite"
  B critiques A: "SQLite is overkill for this, but Flask is simpler. Revised: Flask + JSON with migration path"

Round 3 (parallel, final positions):
  A: "Final: FastAPI + SQLite. I agree with B on simplicity but disagree on storage."
  B: "Final: Flask + JSON. I agree with A on async benefits but disagree on complexity."

Director synthesizes: "Using FastAPI (A's choice, B acknowledged async benefits) with JSON storage
  (B's choice, simpler for MVP) with a documented migration path to SQLite (A's concern addressed)."
```

---

## Knowledge Base (ChromaDB)

The knowledge base is the **company wiki**. Every agent can read and write to it
at any point during their work via MCP tools. One collection per user, all projects
together — cross-project learning happens naturally via semantic similarity.

### MCP tools (available to all agents)

```
query_knowledge(query, limit?)
  → Searches the entire knowledge base for this user
  → Returns relevant documents ranked by semantic similarity
  → Agent can call this multiple times during a single run

store_knowledge(content, work_type, tags?)
  → Saves knowledge for future reference
  → work_type: "requirements_spec", "adr", "plan", "implementation_note",
    "review_feedback", "delivery_report", "clarification", "debug_note"
  → tags: free-form list for additional context (e.g. ["contact-book", "cli", "python"])
```

### What each role stores

| Role | Stores | Example |
|------|--------|---------|
| Director | Requirements specs, clarification Q&A, delivery reports | "Contact book: CRUD CLI, JSON storage, pytest tests" |
| Architect | ADRs, design rationale, rejected approaches | "Chose FastAPI over Flask because async needed for future websocket support" |
| Manager | Task plans, what decomposition worked | "CLI projects work best split into: core module, CLI interface, tests, push" |
| Engineer | Implementation notes, patterns used, gotchas | "JSON file locking: use fcntl.flock on write, no locking on read" |
| Reviewer | Common issues found, quality patterns | "Repeatedly missing: input validation on CLI args" |

### When to query

Agents are instructed to query the knowledge base:
- **Before proposing** — check what already exists for this project/domain
- **When stuck** — search for similar problems and how they were solved
- **During review** — check if known issues are addressed
- **When making decisions** — check if this was decided before

### No upfront injection

The spawner does NOT pre-inject knowledge into the prompt. Agents query what they
need, when they need it. This keeps prompts lean and lets agents make targeted queries
rather than getting a dump of potentially irrelevant context.

---

## Quality enforcement

- **No code without approved spec** — Phase 1 gates Phase 3
- **No code without debated architecture** — Phase 2 gates Phase 3
- **No merge without peer review** — every PR reviewed by a separate agent
- **No delivery without integration review** — Architect checks the whole thing
- **No delivery without requirement mapping** — Director traces every requirement to code
- **Escalation after 3 failures** — if an engineer fails 3 times, escalate to Manager
