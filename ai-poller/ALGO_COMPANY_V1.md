# Company v1 Algorithm — Spec

## Philosophy

Model a software company. You are the CEO. You send requests, the company delivers.
Every decision is debated by two agents before being finalized. The company clarifies
before building and reviews everything heavily.

**Priorities**: Clarification > Quality > Speed

**Core principle**: Every role is a debate pair. Two agents propose independently,
critique each other, and iterate until they converge. This produces higher quality
outputs than any single agent.

---

## The Debate Primitive

The fundamental unit of work in Company v1. Every role uses this.

### How it works

```
Round 1 (parallel):
  Agent A proposes independently
  Agent B proposes independently

Round 2+ (parallel, after reading each other):
  Agent A reads B's position → critiques, steals good ideas, revises
  Agent B reads A's position → critiques, steals good ideas, revises
  Both call declare_position(agree_with_other, disagreements, position)

Convergence check:
  If both agents' disagreements are empty → CONVERGED → parent synthesizes
  If not converged and under round limit → next round
  If not converged and at limit → parent synthesizes anyway (notes non-consensus)
```

### Convergence detection

Each agent calls `declare_position` at the end of every round:

```
declare_position(
  agree_with_other: bool,
  disagreements: ["list of remaining disagreements"],
  position: "full current position text"
)
```

**Converged** = both agents call with `agree_with_other=true` AND `disagreements=[]`.
Parent is notified and writes the synthesis.

### Round limits

```json
{
  "config": {
    "debate_rounds": {
      "director": 0,
      "architect": 0,
      "manager": 5,
      "engineer": 3,
      "reviewer": 3,
      "integration": 0
    },
    "max_debate_rounds": 10,
    "debate_timeout_minutes": 30
  }
}
```

- `0` = no limit, debate until convergence (capped by `max_debate_rounds`)
- `N` = max N rounds, converge early if possible
- `1` = one round each, minimal debate (fast mode)
- `max_debate_rounds` = hard safety cap even for unlimited debates (default 10)
- `debate_timeout_minutes` = force synthesis after this long (default 30)

### Debate state tracking

Stored in the parent task's `props["debate"]`:

```json
{
  "debate": {
    "round": 2,
    "max_rounds": 0,
    "a_task_id": "...",
    "b_task_id": "...",
    "a_done_round": 2,
    "b_done_round": 2,
    "a_converged": false,
    "b_converged": true,
    "started_at": 1234567890
  }
}
```

### What happens when they don't converge

Parent synthesizes and notes: "Agents did not reach consensus after N rounds.
[Role] decided based on the strongest arguments from both sides." This is normal —
if two architects can't agree, the Director makes the call.

### Task tree for a debate

```
[Task: Clarify requirements] (role: director, state: debating)
  ├── [Director-A] (role: debater)
  └── [Director-B] (role: debater)
```

Both debaters post on their own tasks. Each reads the other's task via
`get_task_comments(other_task_id)`. The parent reads both after convergence.

---

## Roles

Every role is a debate pair. The parent of each debate writes the synthesis.

| Role | Debate pair | Synthesized by | Output |
|------|------------|---------------|--------|
| **Director** | Director-A + Director-B | CEO (or auto) | Requirements spec |
| **Architect** | Architect-A + Architect-B | Director | Architecture Decision Record |
| **Manager** | Manager-A + Manager-B | Director | Task plan with acceptance criteria |
| **Engineer** | Engineer-A + Engineer-B | Manager | Implementation approach → one executes |
| **Reviewer** | Reviewer-A + Reviewer-B | Manager | Review decision (approve/reject with feedback) |
| **Integration** | Integration-A + Integration-B | Director | Holistic sign-off or gap list |

---

## Phases

### Phase 1: CLARIFICATION (Director debate)

**State**: `clarifying`

Director-A and Director-B independently read the request and propose clarifying
questions. They debate what needs clarification and converge on:
- What to build
- What NOT to build (non-goals)
- Success criteria
- Constraints
- Key clarifying questions for the CEO

**Synthesis**: Director posts the converged questions to the CEO as a proposal.
CEO answers. Director may follow up with more questions.

When confident, the Directors debate the **requirements spec** and converge.
Synthesized spec posted as proposal.

**State**: `spec_proposed` → CEO approves → Phase 2

---

### Phase 2: ARCHITECTURE (Architect debate)

**State**: `architecting`

Architect-A and Architect-B independently:
1. Query the knowledge base for past decisions on similar projects
2. Read the requirements spec
3. Propose a technical approach

They debate across `debate_rounds.architect` rounds (default: unlimited until convergence).

Each round they must:
- Explicitly state what they agree/disagree with from the other
- Incorporate good ideas from the other
- Challenge assumptions
- Call `declare_position` with current stance

**Synthesis**: Director reads both final positions and writes an ADR:
- Decision (synthesized from both)
- Alternatives considered
- Why this approach won
- Risks acknowledged
- Stores ADR to knowledge base

**State**: `arch_proposed` → CEO approves (or auto-approve) → Phase 3

---

### Phase 3: PLANNING (Manager debate)

**State**: `planning`

Manager-A and Manager-B independently read:
- Requirements spec
- ADR
- Knowledge base (past plans for similar projects)

They debate how to break the work into tasks:
- What subtasks to create
- What order (dependencies)
- Acceptance criteria for each
- Which can run in parallel

**Synthesis**: Director reads both plans, synthesizes the best, posts as proposal.
Director + one Architect review for completeness.

**State**: `plan_proposed` → approved → `plan_approved`

Manager creates actual subtasks → `implementing`

---

### Phase 4: IMPLEMENTATION (Engineer debates, parallel)

**State**: `implementing`

For each subtask, the Manager creates an Engineer debate pair.

**Engineer debate** (per subtask):
- Engineer-A and Engineer-B independently propose implementation approaches
- They debate: which patterns, which libraries, which structure
- They converge on the approach
- Manager synthesizes → picks one engineer to execute

**Execution** (single agent):
- The chosen engineer implements the synthesized approach
- Creates a branch, writes code, runs tests, opens a PR
- Calls `submit_proof` with PR link

**Reviewer debate** (per PR):
- Reviewer-A and Reviewer-B independently review the PR
- They debate: is it correct? edge cases? test coverage? code quality?
- They converge on: approve, or reject with specific feedback
- Manager synthesizes the review → approves PR or sends back to engineer

If rejected → engineer fixes → reviewers re-debate.

---

### Phase 5: INTEGRATION REVIEW (Integration debate)

**State**: `integration_review`

After all PRs are merged:

Integration-A and Integration-B independently review the complete codebase:
- Does it match the ADR?
- Is the code cohesive across PRs?
- Are there architectural violations?
- Any missing pieces?
- Do all tests pass together?

They debate and converge on: sign off, or list of gaps.

**Synthesis**: Director reads the integration review.
- If gaps → new subtasks created → back to `implementing`
- If approved → Phase 6

**State**: `review_complete`

---

### Phase 6: DELIVERY (Director — no debate, just assembly)

**State**: `delivering`

Director writes the delivery report:
- Original request
- Requirements spec
- Architecture decision
- What was built (PR links, files, features)
- Requirement → deliverable mapping
- What was NOT built (confirmed non-goals)
- Knowledge base entries created

Posts as proposal.

**State**: `delivered` → CEO reviews and closes

---

## States (12)

| State | Owner | What's happening |
|-------|-------|-----------------|
| `clarifying` | Director pair | Debating clarifications + spec |
| `spec_proposed` | Director | Spec posted, waiting for CEO |
| `architecting` | Architect pair | Debating architecture |
| `arch_proposed` | Director | ADR posted, waiting for approval |
| `planning` | Manager pair | Debating task plan |
| `plan_proposed` | Director | Plan posted, waiting for approval |
| `implementing` | Engineer pairs | Debating + implementing + reviewing PRs |
| `integration_review` | Integration pair | Debating holistic review |
| `review_complete` | Director | Integration approved |
| `delivering` | Director | Writing delivery report |
| `delivered` | Director | Report posted, waiting for CEO |
| `awaiting_input` | Any | Escalated question, waiting for answer |

---

## Escalation

```
Engineer debate stuck → Manager synthesizes even without convergence
Manager debate stuck → Director synthesizes
Architect debate stuck → Director synthesizes
Any role has a question → parent debate synthesizes an answer
Parent can't answer → escalates up the chain
Director can't answer → asks CEO

CEO is only bothered for:
  1. Clarification answers (Phase 1)
  2. Spec approval (Phase 1)
  3. Architecture approval (Phase 2, unless auto-approve)
  4. Delivery acceptance (Phase 6)
  5. Genuine blockers escalated from Director
```

---

## MCP tools for debates

### Debate-specific tools (algo server)

```
declare_position(agree_with_other, disagreements, position)
  → Records agent's current stance
  → System checks for convergence after both agents declare

read_other_position(debate_partner_task_id)
  → Reads the other debater's latest position
  → Convenience wrapper around get_task_comments
```

### All agents also have

```
query_knowledge(query, limit?)
  → Search company knowledge base at any point

store_knowledge(content, work_type, tags?)
  → Save to knowledge base for future reference

propose_plan / submit_proof / request_clarification
  → Standard workflow tools
```

---

## Knowledge Base usage

Every role queries and stores knowledge throughout their work:

| Phase | Queries | Stores |
|-------|---------|--------|
| Clarification | Past specs for similar projects | Final spec, Q&A |
| Architecture | Past ADRs, patterns, rejected approaches | ADR, debate summary |
| Planning | Past plans, what decomposition worked | Plan, task structure |
| Implementation | Past code patterns, gotchas | Implementation notes |
| Review | Past review feedback, common issues | Review feedback |
| Integration | Full project knowledge | Integration findings |
| Delivery | Everything (for the report) | Delivery report |

---

## Configuration defaults

```json
{
  "algorithm": "company_v1",
  "config": {
    "debate_rounds": {
      "director": 0,
      "architect": 0,
      "manager": 5,
      "engineer": 3,
      "reviewer": 3,
      "integration": 0
    },
    "max_debate_rounds": 10,
    "debate_timeout_minutes": 30,
    "auto_approve_architecture": false
  }
}
```

### Quality presets

```
"quality": "fast"     → all rounds = 1 (minimal debate)
"quality": "standard" → director=2, architect=3, others=2
"quality": "thorough" → director=0, architect=0, manager=5, engineer=3, reviewer=3, integration=0
```

---

## Estimated agent runs

For a 3-subtask project with "thorough" quality:

| Phase | Debates | Rounds (avg) | Runs per debate | Total |
|-------|---------|-------------|----------------|-------|
| Director clarification | 1 | 3 | 7 | 7 |
| Architect | 1 | 4 | 9 | 9 |
| Manager planning | 1 | 3 | 7 | 7 |
| 3 Engineer debates | 3 | 2 | 5 each | 15 |
| 3 Executions | 3 | - | 1 each | 3 |
| 3 Reviewer debates | 3 | 2 | 5 each | 15 |
| Integration debate | 1 | 3 | 7 | 7 |
| Director delivery | 1 | - | 1 | 1 |
| CEO interactions | - | - | ~3 | 3 |
| **Total** | | | | **~67** |

At 2-3 minutes per run: **~2-3 hours end-to-end**, running autonomously.

---

## Task tree example

```
[Build a contact book CLI] (company_v1)
  ├── [Director-A] (debater, clarification)
  ├── [Director-B] (debater, clarification)
  ├── [Architect-A] (debater, architecture)
  ├── [Architect-B] (debater, architecture)
  ├── [Engineer: Core module]
  │     ├── [Engineer-A] (debater)
  │     ├── [Engineer-B] (debater)
  │     ├── [Reviewer-A] (debater)
  │     └── [Reviewer-B] (debater)
  ├── [Engineer: CLI interface]
  │     ├── [Engineer-A] (debater)
  │     ├── [Engineer-B] (debater)
  │     ├── [Reviewer-A] (debater)
  │     └── [Reviewer-B] (debater)
  ├── [Engineer: Tests]
  │     ├── [Engineer-A] (debater)
  │     ├── [Engineer-B] (debater)
  │     ├── [Reviewer-A] (debater)
  │     └── [Reviewer-B] (debater)
  └── [Integration Review]
        ├── [Integration-A] (debater)
        └── [Integration-B] (debater)
```
