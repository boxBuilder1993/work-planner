"""Decompose & Delegate v2 — Clean SDLC cycle.

7 states: planning, plan_approved, managing, working, work_approved,
proof_submitted, awaiting_input.

Every level follows: Plan → Approve → Execute → Deliver → Accept.
Denied proof goes back to planning. PRs required for proof.
"""

from __future__ import annotations

import logging
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
    latest_proposal_denied,
    has_proposal_resolved,
    has_new_user_reply,
    _is_own_proposal,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# v1 compatibility
# ---------------------------------------------------------------------------

STATUS_ALIASES = {
    "needs_planning": "planning",
    "plan_proposed": "planning",
    "in_progress": "managing",
    "worker_ready": "working",
    "work_proposed": "working",
    "implementing": "work_approved",
    "planning_complete": "managing",
}

# ---------------------------------------------------------------------------
# Completed statuses for manager review
# ---------------------------------------------------------------------------

_COMPLETED_STATUSES = frozenset({"done", "complete", "proof_submitted"})

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_KNOWLEDGE_INSTRUCTION = """
KNOWLEDGE BASE: You have access to a company knowledge base via query_knowledge and store_knowledge.
- Before proposing: query_knowledge to check for past decisions and patterns on similar work.
- After making decisions: store_knowledge to save your decisions for future reference.
Use these throughout your work, not just once."""

_PLANNER_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

User comments:
{user_comments}
{denied_block}
{existing_children_block}
You are in PLANNING mode. Think like a tech lead organizing work for your team.
""" + _KNOWLEDGE_INSTRUCTION + """

1. Query the knowledge base for past decisions on similar projects.
2. Explore the task — read repos, understand context, gather information.
3. Decide how to organize the work.

YOUR DEFAULT IS TO DECOMPOSE. Only propose worker-ready if the task is truly a
single small change (one function, one bug fix, one test file).

Call propose_plan with your proposed decomposition or worker-ready justification.
Do NOT create subtasks yet — propose first, wait for approval.
If you need clarification, call request_clarification.

Your task ID is: {task_id}\
"""

_PLAN_EXECUTION_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

Your approved plan:
{approved_plan}

Execute the approved plan:
- If decomposing: create subtasks using create_task (ai_enabled=true, parent_id="{task_id}"),
  then call mark_as_planned.
- If worker-ready: call mark_as_worker_ready.

IMPORTANT: Each subtask description MUST include:
- The target repository (GitHub URL or local path)
- The base branch to work from
- Specific deliverables and acceptance criteria
- Any dependencies on other subtasks

Your task ID is: {task_id}\
"""

_WORKER_PROPOSE_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

Previous activity:
{history}
{denied_block}
""" + _KNOWLEDGE_INSTRUCTION + """

Before doing any work, propose your implementation plan.

1. Query the knowledge base for past implementation patterns and gotchas.
2. Call propose_work with:
   - The target repository and feature branch name
   - The specific files you'll create or modify
   - The PR you'll open (branch → main)
   - Any commands you'll run
   - Expected test results

Do NOT write code or push yet. Propose first, wait for approval.
If you need clarification, call request_clarification.

Your task ID is: {task_id}\
"""

_WORKER_EXECUTE_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

Previous activity:
{history}

Your work plan has been APPROVED. Execute it now:

1. Query the knowledge base for implementation patterns used in this project.
2. Create a feature branch (do NOT push to main directly).
3. Implement the changes.
4. Run tests.
5. Commit and push the branch.
6. Open a PR against main.
7. Call submit_proof with the PR link and evidence (test output, files changed).
8. Store implementation notes in the knowledge base via store_knowledge.

If you get stuck, call request_clarification.

Your task ID is: {task_id}\
"""

_MANAGER_PROMPT = """\
You are the owner of task: "{title}"
{parent_block}

Your subtasks:
{subtasks_block}

Children needing attention:
{children_attention_block}

You are in MANAGEMENT mode. Review proposals from your subtask agents.
""" + _KNOWLEDGE_INSTRUCTION + """

For each item needing attention:
- PLAN proposals: Does the decomposition make sense? approve_child_proposal or deny_child_proposal.
- WORK proposals: Does the implementation plan look right? Check the branch name, files, approach.
- PROOF proposals: Read the PR diff via GitHub. Verify tests pass. If satisfied: approve + close_subtask.
  If not: deny_child_proposal with feedback (child goes back to planning).
- QUESTION proposals: Answer if you can (deny with answer as feedback). Escalate if you can't.

IMPORTANT: Check your own comment history for unanswered questions you already posted.
Do NOT re-ask the same question.

When ALL subtasks are CLOSED (all PRs merged):
- Call submit_proof with links to all merged PRs and a summary.

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
    mcp_servers: dict = {"algo": create_planning_mcp()}
    github = _github_mcp()
    if github:
        mcp_servers["github"] = github
    return mcp_servers, [
        "mcp__algo__*",
        "mcp__workplanner__get_task",
        "mcp__workplanner__get_subtasks",
        "mcp__workplanner__get_task_comments",
        "mcp__workplanner__query_knowledge",
        "mcp__workplanner__store_knowledge",
        "mcp__github__*",
        "Read", "Glob", "Grep", "Bash",
    ]


def _plan_execution_tools() -> tuple[dict, list[str]]:
    return {"algo": create_plan_execution_mcp()}, [
        "mcp__algo__*",
        "mcp__workplanner__create_task",
        "mcp__workplanner__query_knowledge",
        "mcp__workplanner__store_knowledge",
    ]


def _worker_propose_tools() -> tuple[dict, list[str]]:
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
    mcp_servers: dict = {"algo": create_worker_execute_mcp()}
    mcp_servers["git"] = {"command": "npx", "args": ["-y", "git-mcp-server"]}
    github = _github_mcp()
    if github:
        mcp_servers["github"] = github
    return mcp_servers, [
        "mcp__algo__*",
        "mcp__workplanner__get_task",
        "mcp__workplanner__get_task_comments",
        "mcp__workplanner__query_knowledge",
        "mcp__workplanner__store_knowledge",
        "mcp__git__*",
        "mcp__github__*",
        "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    ]


def _manager_tools() -> tuple[dict, list[str]]:
    mcp_servers: dict = {"algo": create_manager_mcp()}
    github = _github_mcp()
    if github:
        mcp_servers["github"] = github
    return mcp_servers, [
        "mcp__algo__*",
        "mcp__workplanner__get_task",
        "mcp__workplanner__get_subtasks",
        "mcp__workplanner__get_task_comments",
        "mcp__workplanner__query_knowledge",
        "mcp__workplanner__store_knowledge",
        "mcp__github__*",
    ]


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _parent_block(ctx: TaskContext) -> str:
    if ctx.parent:
        return f'Your parent task is: "{ctx.parent.title}" (ID: {ctx.parent.id})'
    return "This is a top-level task (no parent). The user reviews your proposals."


def _description_block(ctx: TaskContext) -> str:
    return f"Description: {ctx.task.description}" if ctx.task.description else ""


def _denied_block(ctx: TaskContext) -> str:
    denied = find_denied_proposals(ctx)
    if not denied:
        return ""
    latest = max(denied, key=lambda c: c.created_at)
    return (
        f"\nYour previous proposal was DENIED:\n"
        f"  Proposal: {latest.text[:500]}\n"
        f"  Feedback: {latest.proposal_feedback or '(no feedback)'}\n"
        f"Address this feedback in your new proposal.\n"
    )


def _existing_children_block(ctx: TaskContext) -> str:
    if not ctx.children:
        return ""
    lines = ["Existing subtasks from previous planning:"]
    for child in ctx.children:
        ai_status = child.props.get("aiStatus", "?")
        lines.append(f"  - {child.title} (status: {child.status}, aiStatus: {ai_status}, ID: {child.id})")
    lines.append("You can close obsolete subtasks, create new ones, or leave working ones alone.")
    return "\n".join(lines) + "\n"


def _subtasks_block(ctx: TaskContext) -> str:
    if not ctx.children:
        return "- (no subtasks)"
    lines = []
    for child in ctx.children:
        ai_status = child.props.get("aiStatus", "?")
        lines.append(f"- {child.title} (status: {child.status}, aiStatus: {ai_status}, ID: {child.id})")
    return "\n".join(lines)


def _children_attention_block(ctx: TaskContext) -> str:
    lines = []

    # Pending proposals on children
    pending = find_pending_child_proposals(ctx)
    for child, proposal in pending:
        lines.append(f"- [{child.title}] PENDING proposal (proposal_id: {proposal.id}): {proposal.text[:300]}")

    # Children completed but not closed
    for child in ctx.children:
        if child.status != "CLOSED" and child.props.get("aiStatus", "") in _COMPLETED_STATUSES:
            if not any(c.id == child.id for c, _ in pending):
                child_comments = ctx.children_comments.get(child.id, [])
                last = child_comments[-1].text[:200] if child_comments else "no comments"
                lines.append(f"- [{child.title}] COMPLETED, needs review (close_subtask subtask_id={child.id}): {last}")

    # All closed?
    if ctx.children and all(c.status == "CLOSED" for c in ctx.children):
        lines.append("- ALL SUBTASKS CLOSED — submit your own proof with submit_proof.")

    return "\n".join(lines) if lines else "(nothing needs attention right now)"


def _approved_plan_text(ctx: TaskContext) -> str:
    approved = find_approved_proposals(ctx)
    if approved:
        latest = max(approved, key=lambda c: c.created_at)
        return latest.text
    return "(no approved plan found)"


def _latest_denial_timestamp(ctx: TaskContext) -> int:
    """Get the timestamp of the most recent denied proposal, or 0 if none."""
    denied = find_denied_proposals(ctx)
    if not denied:
        return 0
    return max(c.created_at for c in denied)


def _find_approved_after_latest_denial(ctx: TaskContext) -> list:
    """Find approved proposals that are newer than the most recent denial."""
    cutoff = _latest_denial_timestamp(ctx)
    return [
        c for c in find_approved_proposals(ctx)
        if c.created_at > cutoff
    ]


def _bump_run_count(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
    return PropsUpdate(self_props={"runCount": ctx.task.props.get("runCount", 0) + 1})


# ---------------------------------------------------------------------------
# Algorithm
# ---------------------------------------------------------------------------

class DecomposeAndDelegateV2(Algorithm):
    name = "decompose_and_delegate_v2"

    def initialize(self, ctx: TaskContext) -> PropsUpdate | None:
        updates: dict = {}

        # New task: set initial state
        if not ctx.task.props.get("aiStatus"):
            updates["aiStatus"] = "planning"
            updates["algorithm"] = self.name

        # Inherit algorithm from parent
        if ctx.parent:
            parent_algo = ctx.parent.props.get("algorithm", "simple_answer")
            child_algo = ctx.task.props.get("algorithm", "simple_answer")
            if child_algo != self.name and parent_algo == self.name:
                updates["algorithm"] = self.name

        # Auto-fix: has children but stuck in planning with no pending proposals
        # BUT don't auto-fix if the latest proposal was denied (re-planning in progress)
        status = updates.get("aiStatus", ctx.task.props.get("aiStatus", "planning"))
        if ctx.children and status == "planning":
            has_pending = any(
                c.comment_type == "PROPOSAL" and c.proposal_status == "PENDING"
                for c in ctx.comments
            )
            has_recent_denial = False
            own_proposals = [c for c in ctx.comments if c.comment_type == "PROPOSAL" and _is_own_proposal(c, ctx)]
            if own_proposals:
                latest = max(own_proposals, key=lambda c: c.created_at)
                has_recent_denial = latest.proposal_status == "DENIED"

            if not has_pending and not has_recent_denial:
                updates["aiStatus"] = "managing"

        return PropsUpdate(self_props=updates) if updates else None

    def evaluate(self, ctx: TaskContext, is_running: bool) -> SpawnPlan | None:
        if is_running:
            logger.info("Task '%s': skipping, already running", ctx.task.title)
            return None

        status = ctx.task.props.get("aiStatus", "planning")
        status = STATUS_ALIASES.get(status, status)
        logger.info("Task '%s': evaluate status=%s, %d comments, %d children",
                     ctx.task.title, status, len(ctx.comments), len(ctx.children))

        if status == "planning":
            pending = find_pending_proposals(ctx)
            if pending:
                logger.info("Task '%s': planning, %d pending proposals — waiting", ctx.task.title, len(pending))
                return None
            approved = _find_approved_after_latest_denial(ctx)
            if approved:
                logger.info("Task '%s': planning, approved proposal found — executing plan", ctx.task.title)
                return self._execute_plan(ctx)
            logger.info("Task '%s': planning, no proposals — spawning planner", ctx.task.title)
            return self._plan(ctx)

        if status == "plan_approved":
            return self._execute_plan(ctx)

        if status == "managing":
            return self._manage(ctx)

        if status == "working":
            if find_pending_proposals(ctx):
                return None
            approved = _find_approved_after_latest_denial(ctx)
            if approved:
                return self._worker_execute(ctx)
            return self._worker_propose(ctx)

        if status == "work_approved":
            run_count = ctx.task.props.get("runCount", 0)
            if run_count > 5:
                logger.warning("Task %s hit retry cap (runCount=%d), resetting to planning",
                               ctx.task.id, run_count)
                plan = self._plan(ctx)
                original_on_complete = plan.on_complete
                def on_retry_cap(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
                    result = original_on_complete(ctx, result_text)
                    props = result.self_props if result else {}
                    props["aiStatus"] = "planning"
                    return PropsUpdate(self_props=props)
                plan.on_complete = on_retry_cap
                return plan
            return self._worker_execute(ctx)

        if status == "proof_submitted":
            if latest_proposal_denied(ctx):
                # Reset to planning before re-planning
                plan = self._plan(ctx)
                original_on_complete = plan.on_complete
                def on_replan(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
                    result = original_on_complete(ctx, result_text)
                    props = result.self_props if result else {}
                    props["aiStatus"] = "planning"
                    return PropsUpdate(self_props=props)
                plan.on_complete = on_replan
                return plan
            return None

        if status == "done":
            if ctx.task.parent_id:
                # Child task completed: submit proof so the parent manager can review and close it
                return self._submit_proof_for_done(ctx)
            else:
                # Top-level task: post a completion notice so the user can review and close
                return self._add_completion_notice(ctx)

        if status == "awaiting_input":
            return self._handle_awaiting_input(ctx)

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
            denied_block=_denied_block(ctx),
            existing_children_block=_existing_children_block(ctx),
            task_id=ctx.task.id,
        )
        return SpawnPlan(
            prompt=prompt,
            tools=_planning_tools(),
            on_complete=_bump_run_count,
            metadata={"algo_tools": ["propose_plan", "request_clarification"]},
        )

    def _execute_plan(self, ctx: TaskContext) -> SpawnPlan:
        prompt = _PLAN_EXECUTION_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            approved_plan=_approved_plan_text(ctx),
            task_id=ctx.task.id,
        )

        approved_plan = _approved_plan_text(ctx)

        def on_plan_executed(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            status = ctx.task.props.get("aiStatus")
            # Normalize legacy statuses (e.g. "plan_proposed" → "planning")
            # so tasks that started with a legacy aiStatus still transition correctly
            # after plan execution. Without this, tasks with aiStatus="plan_proposed"
            # would never match ("plan_approved", "planning") and stay stuck re-planning.
            status = STATUS_ALIASES.get(status, status)
            if status in ("plan_approved", "planning"):
                if ctx.children:
                    return PropsUpdate(self_props={"aiStatus": "managing", "runCount": run_count})
                # Check approved plan intent — does it mention decomposition/subtasks?
                plan_lower = approved_plan.lower()
                if any(kw in plan_lower for kw in ["subtask", "decompos", "break into", "split into"]):
                    # Plan said to decompose but no children created — retry
                    logger.warning("Plan said to decompose but no children created for task %s", ctx.task.id)
                    return PropsUpdate(self_props={"aiStatus": "planning", "runCount": run_count})
                return PropsUpdate(self_props={"aiStatus": "working", "runCount": run_count})
            return PropsUpdate(self_props={"runCount": run_count})

        return SpawnPlan(
            prompt=prompt,
            tools=_plan_execution_tools(),
            on_complete=on_plan_executed,
            metadata={"algo_tools": ["mark_as_planned", "mark_as_worker_ready"]},
        )

    # -- Worker ------------------------------------------------------------

    def _worker_propose(self, ctx: TaskContext) -> SpawnPlan:
        history = format_comment_history(ctx.comments)
        prompt = _WORKER_PROPOSE_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            history=history,
            denied_block=_denied_block(ctx),
            task_id=ctx.task.id,
        )
        return SpawnPlan(
            prompt=prompt,
            tools=_worker_propose_tools(),
            on_complete=_bump_run_count,
            metadata={"algo_tools": ["propose_work", "request_clarification"]},
        )

    def _worker_execute(self, ctx: TaskContext) -> SpawnPlan:
        history = format_comment_history(ctx.comments)
        prompt = _WORKER_EXECUTE_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            history=history,
            task_id=ctx.task.id,
        )
        return SpawnPlan(
            prompt=prompt,
            tools=_worker_execute_tools(),
            on_complete=_bump_run_count,
            metadata={"algo_tools": ["submit_proof", "request_clarification"]},
        )

    # -- Manager -----------------------------------------------------------

    def _manage(self, ctx: TaskContext) -> SpawnPlan | None:
        pending = find_pending_child_proposals(ctx)
        all_closed = all(c.status == "CLOSED" for c in ctx.children) if ctx.children else False
        children_completed = [
            c for c in ctx.children
            if c.status != "CLOSED" and c.props.get("aiStatus", "") in _COMPLETED_STATUSES
        ]

        if not pending and not children_completed and not all_closed:
            return None

        prompt = _MANAGER_PROMPT.format(
            title=ctx.task.title,
            parent_block=_parent_block(ctx),
            subtasks_block=_subtasks_block(ctx),
            children_attention_block=_children_attention_block(ctx),
            task_id=ctx.task.id,
        )
        def on_manage_complete(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            # If all children closed but manager didn't submit proof, force proof_submitted
            all_done = all(c.status == "CLOSED" for c in ctx.children) if ctx.children else False
            current = ctx.task.props.get("aiStatus")
            if all_done and current == "managing":
                logger.info("All children closed for task %s but no proof submitted — forcing proof_submitted", ctx.task.id)
                return PropsUpdate(self_props={"aiStatus": "proof_submitted", "runCount": run_count})
            return PropsUpdate(self_props={"runCount": run_count})

        return SpawnPlan(
            prompt=prompt,
            tools=_manager_tools(),
            on_complete=on_manage_complete,
            metadata={"algo_tools": [
                "approve_child_proposal", "deny_child_proposal",
                "close_subtask", "request_rework",
                "submit_proof", "request_clarification",
            ]},
        )

    # -- Awaiting input ----------------------------------------------------

    def _handle_awaiting_input(self, ctx: TaskContext) -> SpawnPlan | None:
        if has_proposal_resolved(ctx) or has_new_user_reply(ctx):
            resume = ctx.task.props.get("resumeState", "planning")
            resume = STATUS_ALIASES.get(resume, resume)
            if resume == "working":
                return self._worker_propose(ctx)
            if resume == "managing":
                return self._manage(ctx)
            return self._plan(ctx)
        return None

    # -- Done status handlers ---------------------------------------------

    def _submit_proof_for_done(self, ctx: TaskContext) -> SpawnPlan:
        """Child task reached 'done': submit proof so the parent manager can close it."""
        history = format_comment_history(ctx.comments)
        prompt = (
            f'You are the owner of task: "{ctx.task.title}"\n'
            f"{_description_block(ctx)}\n"
            f"{_parent_block(ctx)}\n\n"
            f"Previous activity:\n{history}\n\n"
            "This task has been completed (aiStatus: done). Your parent manager is waiting\n"
            "to review and close your task. Call submit_proof now with a summary of what\n"
            "was accomplished, referencing any PRs, commits, or outputs from the activity above.\n\n"
            f"Your task ID is: {ctx.task.id}"
        )
        return SpawnPlan(
            prompt=prompt,
            tools=_worker_execute_tools(),
            on_complete=_bump_run_count,
            metadata={"algo_tools": ["submit_proof"]},
        )

    def _add_completion_notice(self, ctx: TaskContext) -> SpawnPlan:
        """Top-level task reached 'done': post a completion summary for the user to review."""
        history = format_comment_history(ctx.comments)
        prompt = (
            f'You are the owner of task: "{ctx.task.title}"\n'
            f"{_description_block(ctx)}\n\n"
            f"Previous activity:\n{history}\n\n"
            "This task has been completed (aiStatus: done). The user needs to review\n"
            "your work and manually close the task when satisfied. Call submit_summary\n"
            "with a clear summary of what was accomplished, so the user knows it is ready\n"
            "for review.\n\n"
            f"Your task ID is: {ctx.task.id}"
        )
        return SpawnPlan(
            prompt=prompt,
            tools=_worker_execute_tools(),
            on_complete=_bump_run_count,
            metadata={"algo_tools": ["submit_summary"]},
        )
