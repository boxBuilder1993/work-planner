# Decompose & Delegate v2 — Spec

## Philosophy

Every task follows the same SDLC cycle regardless of depth:

```
Plan → Approve → Execute → Deliver → Accept
```

The parent is always the approver. The user is the approver for top-level tasks.
Every interaction between levels is a proposal on the task's own comment thread.

---

## States (7)

| State | Meaning |
|-------|---------|
| `planning` | Owner explores task, posts a plan proposal, waits for approval |
| `plan_approved` | Plan was approved. Owner creates subtasks (→ managing) or starts work (→ working) |
| `managing` | Owner has children. Reviews child proposals, approves/denies, closes children |
| `working` | Owner will implement directly. Posts work proposal (PRs, commands), waits for approval |
| `work_approved` | Work was approved. Owner implements, then submits proof |
| `proof_submitted` | Owner posted completion proof. Waiting for parent to close or deny |
| `awaiting_input` | Owner asked a question. Frozen until parent answers. `resumeState` tracks where to go back |

---

## Transitions

```
START → planning

planning:
  - No proposals yet → spawn planner (explore, propose)
  - PENDING proposal exists → wait
  - Proposal APPROVED → plan_approved
  - Proposal DENIED → stay in planning, re-plan with feedback

plan_approved:
  - Owner creates subtasks → managing
  - Owner marks as worker-ready → working
  - (fallback: if agent didn't transition, check children exist → managing, else → working)

managing:
  - Children have pending proposals → spawn manager to review
  - Children completed (proof_submitted/done) but not closed → spawn manager to review and close
  - All children CLOSED → owner posts own proof → proof_submitted
  - Manager can't answer a child's question → posts own proposal (escalation) → awaiting_input

working:
  - No proposals yet → spawn worker-proposer (explore, propose specific work)
  - PENDING proposal exists → wait
  - Proposal APPROVED → work_approved
  - Proposal DENIED → stay in working, re-propose with feedback

work_approved:
  - Spawn worker-executor (write code, run tests, open PRs)
  - Agent calls submit_proof → proof_submitted
  - Agent doesn't finish (timeout/crash) → stays work_approved, retries next cycle

proof_submitted:
  - Parent approves + closes task → CLOSED (terminal)
  - Parent DENIES → planning (re-plan from scratch with feedback)

awaiting_input:
  - Question proposal resolved (approved/denied by parent) → resume to resumeState
  - Direct user reply (top-level tasks) → resume to resumeState
```

---

## Denial flows

| What was denied | Current state | Goes to | What happens |
|-----------------|---------------|---------|--------------|
| Plan proposal | planning | planning | Re-plan with denial feedback in prompt |
| Work proposal | working | working | Re-propose with denial feedback in prompt |
| Proof of completion (worker) | proof_submitted | planning | Re-assess from scratch, may decompose |
| Proof of completion (manager) | proof_submitted | planning | Re-assess, may restructure children |

Key principle: **denied proof goes back to planning, not working.** The owner needs to
re-evaluate the approach, not just patch it. It can create new subtasks or restructure.

When a manager re-plans after proof denial, existing children still exist. The planner
prompt includes them and the denial feedback. The agent can close obsolete subtasks,
create new ones, or leave working ones alone.

---

## Tools per state

| State | Algo tools | Other tools |
|-------|-----------|-------------|
| planning | `propose_plan`, `request_clarification` | Read-only code tools, GitHub (explore) |
| plan_approved | `mark_as_planned`, `mark_as_worker_ready` | `create_task` |
| managing | `approve_child_proposal`, `deny_child_proposal`, `close_subtask`, `request_rework`, `submit_proof`, `request_clarification` | Read task/comments |
| working | `propose_work`, `request_clarification` | Read-only code tools, GitHub (explore) |
| work_approved | `submit_proof`, `request_clarification` | Full code tools, git, GitHub |
| proof_submitted | *(none — waiting)* | |
| awaiting_input | *(none — frozen)* | |

---

## evaluate() logic

```python
def evaluate(self, ctx, is_running):
    if is_running:
        return None

    status = ctx.task.props.get("aiStatus", "planning")

    # Normalize old state names
    status = STATUS_ALIASES.get(status, status)

    if status == "planning":
        if find_pending_proposals(ctx):
            return None                         # waiting for approval
        if find_approved_proposals(ctx):
            return self._execute_plan(ctx)      # approved → execute
        return self._plan(ctx)                  # plan (or re-plan after denial)

    if status == "plan_approved":
        return self._execute_plan(ctx)          # create subtasks or mark working

    if status == "managing":
        return self._manage(ctx)                # review children (None if nothing actionable)

    if status == "working":
        if find_pending_proposals(ctx):
            return None                         # waiting for approval
        if find_approved_proposals(ctx):
            return self._worker_execute(ctx)    # approved → implement
        return self._worker_propose(ctx)        # propose (or re-propose after denial)

    if status == "work_approved":
        return self._worker_execute(ctx)        # execute (retries on failure)

    if status == "proof_submitted":
        # Check if proof was denied → back to planning
        if _latest_proposal_denied(ctx):
            return self._plan(ctx)
        return None                             # waiting for parent to close

    if status == "awaiting_input":
        return self._handle_awaiting_input(ctx)

    return None                                 # done, unknown, CLOSED
```

---

## Proposal ownership

A proposal is "own" if it's on this task AND not posted by a child task's ID:

```python
def _is_own_proposal(comment, ctx):
    child_ids = {c.id for c in ctx.children}
    return comment.created_by not in child_ids
```

Used consistently in: `find_pending_proposals`, `find_approved_proposals`,
`find_denied_proposals`, `_latest_proposal_denied`.

Child proposals: any PENDING PROPOSAL on a child's task (regardless of createdBy).

---

## on_complete callbacks

All `on_complete` callbacks just bump `runCount`. State transitions are driven by
MCP tools (the agent calls them) or by `evaluate()` (which reads proposal status).

The only fallback: `plan_approved` on_complete checks if the agent created children
but didn't call `mark_as_planned` → forces `managing`. Or if no children → forces `working`.

---

## Initialization (in algorithm, not processor)

```python
class DecomposeAndDelegateV2(Algorithm):
    def initialize(self, ctx):
        """Called by processor before evaluate(). Handles D&D-specific setup."""
        updates = {}

        # New task: set initial state
        if not ctx.task.props.get("aiStatus"):
            updates["aiStatus"] = "planning"
            updates["algorithm"] = "decompose_and_delegate_v2"

        # Inherit algorithm from parent
        if ctx.parent:
            parent_algo = ctx.parent.props.get("algorithm", "simple_answer")
            if ctx.task.props.get("algorithm") == "simple_answer" and parent_algo == "decompose_and_delegate_v2":
                updates["algorithm"] = "decompose_and_delegate_v2"

        # Auto-fix: has children but stuck in planning → managing
        if ctx.children and ctx.task.props.get("aiStatus") == "planning":
            has_no_pending = not any(
                c.comment_type == "PROPOSAL" and c.proposal_status == "PENDING"
                for c in ctx.comments
            )
            if has_no_pending:
                updates["aiStatus"] = "managing"

        return PropsUpdate(self_props=updates) if updates else None
```

---

## Manager behavior

The manager spawns when:
1. Any child has a PENDING proposal (plan, work, proof, or question)
2. Any child has a completed status but isn't CLOSED (needs review)
3. All children are CLOSED (manager should submit own proof)

The manager prompt includes:
- List of children with their status
- Pending proposals from children (with proposal IDs for approve/deny)
- Children needing review (completed but not closed)
- Whether all children are closed (time to submit proof)

---

## Awaiting input

When `request_clarification` is called:
- Records `resumeState` in props (the current aiStatus before switching)
- Sets `aiStatus = awaiting_input`
- Managers stay in `managing` instead (they can keep reviewing other children)

When the question is answered (proposal resolved or user reply):
- Reads `resumeState` from props
- Returns to that state

---

## Compatibility with v1

The registry supports both:
```python
registry.register(DecomposeAndDelegate())    # v1
registry.register(DecomposeAndDelegateV2())  # v2
```

Users select the algorithm per task via the UI. New tasks can use v2 while existing
v1 tasks continue working. V2 includes a STATUS_ALIASES map for any v1 tasks that
get migrated:

```python
STATUS_ALIASES = {
    "needs_planning": "planning",
    "plan_proposed": "planning",
    "in_progress": "managing",
    "worker_ready": "working",
    "work_proposed": "working",
    "implementing": "work_approved",
    "planning_complete": "managing",
}
```
