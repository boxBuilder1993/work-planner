"""DecomposeAndDelegate algorithm — proposal-based approval flow.

States:
  needs_planning → plan_proposed → (approved) → in_progress | worker_ready
  worker_ready → work_proposed → (approved) → implementing → done
  in_progress → (manages children) → done
  awaiting_input → (proposal resolved) → resumes
"""

from __future__ import annotations

import os

from algo_tools import (
    create_manager_mcp,
    create_plan_execution_mcp,
    create_planning_mcp,
    create_worker_execute_mcp,
    create_worker_propose_mcp,
)
from algorithm import (
    Algorithm,
    TaskContext,
    SpawnPlan,
    PropsUpdate,
    format_comment_history,
    find_approved_proposals,
    find_denied_proposals,
    find_pending_proposals,
    find_pending_child_proposals,
    has_proposal_resolved,
    has_new_user_reply,
)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PLANNER_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

User comments:
{user_comments}

You are in PLANNING mode. Think like a tech lead organizing work for your team.
Assess the scope fresh from the task description — do not rely on any prior agent work.

1. Explore the task — read repos, understand context, gather information.
2. Ask yourself: "If I were running a team, how would I assign this work?"

YOUR DEFAULT ACTION IS TO DECOMPOSE. Only propose worker-ready if the task is
truly a single small change (one function, one bug fix, one test file).

When you've decided, call propose_plan with your proposed decomposition:
- List the subtasks you want to create, with titles and descriptions
- Explain the dependency order
- Or explain why this is worker-ready (single small change)

Do NOT create subtasks yet. Propose first, then wait for approval.
If you need clarification, call request_clarification.

Your task ID is: {task_id}\
"""

_PLAN_EXECUTION_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

Your approved plan:
{approved_plan}

Your plan has been APPROVED. Now execute it:
- If you proposed decomposition: create the subtasks using create_task
  (with ai_enabled=true, parent_id="{task_id}"), then call mark_as_planned.
- If you proposed worker-ready: call mark_as_worker_ready.

Give each subtask a clear title and description specifying what "done" looks like.
Note dependencies in descriptions.

Your task ID is: {task_id}\
"""

_WORKER_PROPOSE_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

Previous activity:
{history}

You are in IMPLEMENTATION mode. Before doing any work, you must propose your plan.

Review the task, explore the codebase, and then call propose_work with:
- The specific files you'll create or modify
- The PR you'll open (branch name, target)
- Any commands you need to run
- The expected outcome

Do NOT write code, push, or run commands yet. Propose first, wait for approval.
If you need clarification, call request_clarification.

Your task ID is: {task_id}\
"""

_WORKER_EXECUTE_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

Previous activity:
{history}

Your work plan has been APPROVED. Execute it now.
Write code, run tests, open PRs as described in your approved plan.

When done, call submit_proof (or submit_summary for top-level tasks) with:
- PR links
- Command outputs / test results
- Files changed

If you get stuck, call request_clarification.

Your task ID is: {task_id}\
"""

_MANAGER_PROMPT = """\
You are the owner of task: "{title}"
{parent_block}

Your subtasks:
{subtasks_block}

Children with pending proposals:
{pending_proposals_block}

You are in MANAGEMENT mode. Review proposals from your subtask agents.

For each pending proposal, read it carefully and decide:
- PLAN proposals: Does the decomposition make sense? approve_child_proposal or deny_child_proposal with feedback.
- WORK proposals: Does the implementation plan look right? Approve or deny.
- PROOF proposals: Verify the evidence. If satisfied, approve and then close_subtask. If not, request_rework.
- QUESTION proposals: If you can answer, deny with the answer as feedback. If you can't, call request_clarification to escalate to YOUR parent.

IMPORTANT: Check your own comment history for any unanswered QUESTION proposals you
already posted. If you have a pending question to your parent, do NOT re-ask it.
Focus on handling the children's proposals you CAN answer independently.

When ALL subtasks are closed:
- Call submit_proof (or submit_summary for top-level) with overall results.

Your task ID is: {task_id}\
"""


# ---------------------------------------------------------------------------
# Tool sets
# ---------------------------------------------------------------------------

def _github_mcp() -> dict | None:
    token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not token:
        return None
    return {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": token},
    }


def _planning_tools() -> tuple[dict, list[str]]:
    """Planner: propose_plan + read-only exploration."""
    mcp_servers: dict = {"algo": create_planning_mcp()}
    github = _github_mcp()
    if github:
        mcp_servers["github"] = github
    return mcp_servers, [
        "mcp__algo__*",
        "mcp__workplanner__get_task",
        "mcp__workplanner__get_subtasks",
        "mcp__workplanner__get_task_comments",
        "mcp__github__*",
        "Read", "Glob", "Grep", "Bash",
    ]


def _plan_execution_tools() -> tuple[dict, list[str]]:
    """After plan approval: create subtasks + mark_as_planned/worker_ready."""
    mcp_servers: dict = {"algo": create_plan_execution_mcp()}
    return mcp_servers, [
        "mcp__algo__*",
        "mcp__workplanner__create_task",
    ]


def _worker_propose_tools() -> tuple[dict, list[str]]:
    """Worker proposing: read-only exploration + propose_work."""
    mcp_servers: dict = {"algo": create_worker_propose_mcp()}
    github = _github_mcp()
    if github:
        mcp_servers["github"] = github
    return mcp_servers, [
        "mcp__algo__*",
        "mcp__workplanner__get_task",
        "mcp__workplanner__get_task_comments",
        "mcp__github__*",
        "Read", "Glob", "Grep", "Bash",
    ]


def _worker_execute_tools() -> tuple[dict, list[str]]:
    """Worker executing approved work: full code tools."""
    mcp_servers: dict = {"algo": create_worker_execute_mcp()}
    mcp_servers["git"] = {
        "command": "npx",
        "args": ["-y", "git-mcp-server"],
    }
    github = _github_mcp()
    if github:
        mcp_servers["github"] = github
    return mcp_servers, [
        "mcp__algo__*",
        "mcp__workplanner__get_task",
        "mcp__workplanner__get_task_comments",
        "mcp__git__*",
        "mcp__github__*",
        "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    ]


def _manager_tools() -> tuple[dict, list[str]]:
    """Manager: review children, approve/deny, close/rework."""
    return {"algo": create_manager_mcp()}, [
        "mcp__algo__*",
        "mcp__workplanner__get_task",
        "mcp__workplanner__get_subtasks",
        "mcp__workplanner__get_task_comments",
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parent_block(ctx: TaskContext) -> str:
    if ctx.parent:
        return f'Your parent task is: "{ctx.parent.title}" (ID: {ctx.parent.id})'
    return "This is a top-level task (no parent). The user reviews your proposals."


def _description_block(ctx: TaskContext) -> str:
    return f"Description: {ctx.task.description}" if ctx.task.description else ""


def _subtasks_block(ctx: TaskContext) -> str:
    if not ctx.children:
        return "- (no subtasks)"
    lines = []
    for child in ctx.children:
        ai_status = child.props.get("aiStatus", "?")
        lines.append(f"- {child.title} (status: {child.status}, aiStatus: {ai_status}, ID: {child.id})")
    return "\n".join(lines)


def _pending_proposals_block(ctx: TaskContext) -> str:
    pending = find_pending_child_proposals(ctx)
    if not pending:
        return "(none)"
    lines = []
    for child, proposal in pending:
        lines.append(f"- [{child.title}] (proposal_id: {proposal.id}): {proposal.text[:300]}")
    return "\n".join(lines)


def _approved_plan_text(ctx: TaskContext) -> str:
    approved = find_approved_proposals(ctx)
    if approved:
        return approved[-1].text
    return "(no approved plan found)"


def _bump_run_count(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
    run_count = ctx.task.props.get("runCount", 0) + 1
    return PropsUpdate(self_props={"runCount": run_count})


# ---------------------------------------------------------------------------
# Algorithm
# ---------------------------------------------------------------------------

class DecomposeAndDelegate(Algorithm):
    name = "decompose_and_delegate"

    def evaluate(self, ctx: TaskContext, is_running: bool) -> SpawnPlan | None:
        if is_running:
            return None

        status = ctx.task.props.get("aiStatus", "needs_planning")

        if status == "needs_planning":
            return self._plan(ctx)
        if status == "plan_proposed":
            return self._handle_plan_proposed(ctx)
        if status == "worker_ready":
            return self._worker_propose(ctx)
        if status == "work_proposed":
            return self._handle_work_proposed(ctx)
        if status == "implementing":
            return self._worker_execute(ctx)
        if status == "in_progress":
            return self._manage(ctx)
        if status == "awaiting_input":
            return self._handle_awaiting_input(ctx)
        # "proof_submitted" or "done" → waiting for parent, nothing to do
        return None

    # -- Planning ----------------------------------------------------------

    def _plan(self, ctx: TaskContext) -> SpawnPlan:
        user_only = [c for c in ctx.comments if c.created_by == "user"]
        user_comments = format_comment_history(user_only) if user_only else "(none)"
        prompt = _PLANNER_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            user_comments=user_comments,
            task_id=ctx.task.id,
        )
        return SpawnPlan(prompt=prompt, tools=_planning_tools(), on_complete=_bump_run_count)

    def _handle_plan_proposed(self, ctx: TaskContext) -> SpawnPlan | None:
        approved = find_approved_proposals(ctx)
        if approved:
            # Plan approved → execute it
            prompt = _PLAN_EXECUTION_PROMPT.format(
                title=ctx.task.title,
                description_block=_description_block(ctx),
                parent_block=_parent_block(ctx),
                approved_plan=_approved_plan_text(ctx),
                task_id=ctx.task.id,
            )
            return SpawnPlan(prompt=prompt, tools=_plan_execution_tools(), on_complete=_bump_run_count)

        denied = find_denied_proposals(ctx)
        if denied:
            # Denied → re-plan with feedback in history
            return self._plan(ctx)

        # Still waiting for approval
        return None

    # -- Worker proposal ---------------------------------------------------

    def _worker_propose(self, ctx: TaskContext) -> SpawnPlan:
        history = format_comment_history(ctx.comments)
        prompt = _WORKER_PROPOSE_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            history=history,
            task_id=ctx.task.id,
        )
        return SpawnPlan(prompt=prompt, tools=_worker_propose_tools(), on_complete=_bump_run_count)

    def _handle_work_proposed(self, ctx: TaskContext) -> SpawnPlan | None:
        approved = find_approved_proposals(ctx)
        if approved:
            # Work approved → execute
            return self._worker_execute(ctx)

        denied = find_denied_proposals(ctx)
        if denied:
            # Denied → re-propose
            return self._worker_propose(ctx)

        return None

    # -- Worker execution --------------------------------------------------

    def _worker_execute(self, ctx: TaskContext) -> SpawnPlan:
        history = format_comment_history(ctx.comments)
        prompt = _WORKER_EXECUTE_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            history=history,
            task_id=ctx.task.id,
        )

        def on_complete(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            # If agent didn't call submit_proof, set to implementing so it retries
            status = ctx.task.props.get("aiStatus")
            if status != "proof_submitted":
                return PropsUpdate(self_props={"aiStatus": "implementing", "runCount": run_count})
            return PropsUpdate(self_props={"runCount": run_count})

        return SpawnPlan(prompt=prompt, tools=_worker_execute_tools(), on_complete=on_complete, model="claude-sonnet-4-6")

    # -- Manager -----------------------------------------------------------

    def _manage(self, ctx: TaskContext) -> SpawnPlan | None:
        pending = find_pending_child_proposals(ctx)
        all_closed = all(c.status == "CLOSED" for c in ctx.children) if ctx.children else False

        if not pending and not all_closed:
            return None

        prompt = _MANAGER_PROMPT.format(
            title=ctx.task.title,
            parent_block=_parent_block(ctx),
            subtasks_block=_subtasks_block(ctx),
            pending_proposals_block=_pending_proposals_block(ctx),
            task_id=ctx.task.id,
        )
        return SpawnPlan(prompt=prompt, tools=_manager_tools(), on_complete=_bump_run_count)

    # -- Awaiting input ----------------------------------------------------

    def _handle_awaiting_input(self, ctx: TaskContext) -> SpawnPlan | None:
        # Unblock when our proposal is resolved (approved/denied by parent)
        if has_proposal_resolved(ctx):
            # Determine which phase to resume based on the resolved proposal
            denied = find_denied_proposals(ctx)
            if denied:
                latest_denied = max(denied, key=lambda c: c.created_at)
                if "[QUESTION]" in latest_denied.text:
                    # Question answered — resume planning
                    return self._plan(ctx)
            # Default: resume planning
            return self._plan(ctx)

        # Also unblock on direct user reply (for top-level tasks)
        if has_new_user_reply(ctx):
            return self._plan(ctx)

        return None
