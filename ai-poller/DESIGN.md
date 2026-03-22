# AI Poller — Decompose & Delegate Redesign

## Implementation Tasks

### 1. Rework proposal location
- Proposals live on the task that created them (owner posts on own task)
- Parent watches children's tasks for proposals
- Update `find_pending_child_proposals` to scan children's tasks, not parent's task
- Update `submit_proof` / `submit_for_review` to post on own task, not parent task

### 2. Add `propose_plan` tool
- New MCP tool: posts a PROPOSAL on the owner's own task describing the plan
- Required `reason` field explaining the decomposition or implementation approach
- Sets `aiStatus: "plan_proposed"`
- Available in planning phase

### 3. Add `plan_proposed` state to D&D algorithm
- `evaluate()` handles `plan_proposed`: check if own proposal was approved/denied
- Approved → re-spawn to execute (create subtasks or implement)
- Denied → re-spawn in `needs_planning` with feedback in comment history

### 4. Remove direct subtask creation from planner
- Planner can only `propose_plan` or `request_clarification`
- Remove `create_task` and `mark_as_planned` from planner tool set
- After plan approval, re-spawn with `create_task` + `mark_as_planned` access

### 5. Rework manager to watch children's tasks
- Manager scans each child task for pending proposals (not its own task)
- New MCP tools: `approve_child_proposal(child_task_id, proposal_id)`, `deny_child_proposal(child_task_id, proposal_id, feedback)`
- Manager reads child proposals via `get_task_comments(child_task_id)`
- Remove old `get_pending_proposals` usage that looked at parent task

### 6. Rework escalation flow
- `request_clarification` becomes a PROPOSAL on own task (question type)
- Sets `aiStatus: "awaiting_input"`
- Parent manager sees it as a child proposal, answers or escalates further
- When proposal is resolved (approved/denied), child resumes

### 7. Update `awaiting_input` unblock logic
- Currently checks for user comments
- Change to: check if the task's most recent PENDING proposal has been resolved
- Resolved = approved or denied (denial feedback = the answer)

### 8. Update manager spawning logic
- Manager spawns when ANY child has a pending proposal (plan, proof, or question)
- `should_spawn` for `in_progress`: scan children's tasks for pending proposals
- Manager prompt includes list of children with pending proposals

### 9. Update prompts
- Planner prompt: "propose your plan, don't create subtasks directly"
- Manager prompt: "scan your children's tasks for proposals, approve/deny/escalate"
- Worker prompt: "post proof on your own task when done"
- All prompts: clarify escalation mechanism (propose on own task for parent to see)

### 10. Update `processor.py` context building
- `TaskContext` needs children's comments, not just the task's own comments
- Add `children_comments: dict[str, list[CommentEntity]]` to TaskContext
- Processor fetches comments for each child task

### 11. Test the full flow
- Create an ai-enabled task with D&D algorithm
- Verify: planner proposes → user approves → subtasks created
- Verify: child planner proposes → parent manager approves
- Verify: worker completes → proof posted → manager closes child
- Verify: escalation flows up the chain
- Verify: all children closed → parent posts completion → user closes

## State Machine

```
needs_planning → plan_proposed → (approved) → in_progress | worker_ready
                               → (denied)  → needs_planning

worker_ready   → (implements) → done

in_progress    → (manages children) → done

awaiting_input → (proposal resolved) → previous phase

done           → (parent closes)
```

## Tool Access by Phase

| Phase | Tools |
|-------|-------|
| Planning (needs_planning) | propose_plan, request_clarification, read-only code, GitHub |
| Plan execution (after approval) | create_task, mark_as_planned, mark_as_worker_ready |
| Worker (worker_ready) | submit_proof, submit_summary, request_clarification, full code, git, GitHub |
| Manager (in_progress) | approve_child_proposal, deny_child_proposal, close_subtask, request_rework, submit_proof, submit_summary, request_clarification |
