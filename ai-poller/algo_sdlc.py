"""SDLC Algorithm — Clean 4-state lifecycle.

States: plan → execute → manage → done (+ awaiting_input)

Every task follows: Think → Approve → Do → Review.
The debate layer handles quality automatically.
"""

from __future__ import annotations

import logging
import os

from algo_tools import (
    create_manager_mcp,
    create_plan_execution_mcp,
    create_planning_mcp,
    create_worker_execute_mcp,
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
# Completed statuses for manager review
# ---------------------------------------------------------------------------

_COMPLETED = frozenset({"done", "proof_submitted", "complete"})

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PLAN_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}
{context_block}

You have access to a company knowledge base via query_knowledge and store_knowledge.
Query it for past decisions and patterns before proposing.

Assess this task:
- If it needs multiple pieces of work: propose a decomposition into subtasks.
  List each subtask with a title, description, deliverables, and dependencies.
- If it's a single focused change: propose an implementation plan.
  Include the target repo, branch, files to change, and expected outcome.

Call propose_plan with your proposal. Wait for approval before acting.
If you need clarification, call request_clarification.

Your task ID is: {task_id}\
"""

_EXECUTE_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

Approved plan:
{approved_plan}

Execute this plan now:
- If decomposing: create subtasks using create_task (ai_enabled=true, parent_id="{task_id}").
  Each subtask MUST include: target repo, base branch, deliverables, acceptance criteria.
  Then call mark_as_planned.
- If implementing: create a feature branch, implement, run tests, open a PR.
  Call submit_proof with the PR link and evidence.

Store your decisions in the knowledge base via store_knowledge.

Your task ID is: {task_id}\
"""

_MANAGE_PROMPT = """\
You are the manager of task: "{title}"
{parent_block}

Subtasks:
{subtasks_block}

Items needing attention:
{attention_block}

Review proposals from your subtasks:
- Plan proposals: approve if the decomposition/approach makes sense. Deny with feedback if not.
- Proof proposals: review the PR via GitHub. Check code quality and tests. Approve + close_subtask if good. Deny if not (child re-plans from scratch).
- Questions: answer if you can (deny with the answer as feedback). If you can't, call request_clarification to escalate to your parent.

When ALL subtasks are CLOSED:
- Call submit_proof with a summary of what was delivered and links to all PRs.

Query the knowledge base for context. Store review decisions for future reference.

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


_WP_TOOLS = [
    "mcp__workplanner__get_task",
    "mcp__workplanner__get_subtasks",
    "mcp__workplanner__get_task_comments",
    "mcp__workplanner__query_knowledge",
    "mcp__workplanner__store_knowledge",
]


def _plan_tools() -> tuple[dict, list[str]]:
    mcp: dict = {"algo": create_planning_mcp()}
    gh = _github_mcp()
    if gh:
        mcp["github"] = gh
    return mcp, ["mcp__algo__*", *_WP_TOOLS, "mcp__github__*", "Read", "Glob", "Grep", "Bash"]


def _execute_tools() -> tuple[dict, list[str]]:
    mcp: dict = {"algo": create_plan_execution_mcp()}
    mcp["git"] = {"command": "npx", "args": ["-y", "git-mcp-server"]}
    gh = _github_mcp()
    if gh:
        mcp["github"] = gh
    return mcp, [
        "mcp__algo__*", "mcp__workplanner__create_task", *_WP_TOOLS,
        "mcp__git__*", "mcp__github__*",
        "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    ]


def _manage_tools() -> tuple[dict, list[str]]:
    mcp: dict = {"algo": create_manager_mcp()}
    gh = _github_mcp()
    if gh:
        mcp["github"] = gh
    return mcp, ["mcp__algo__*", *_WP_TOOLS, "mcp__workplanner__get_subtasks", "mcp__github__*"]


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _parent_block(ctx: TaskContext) -> str:
    if ctx.parent:
        return f'Your parent task is: "{ctx.parent.title}" (ID: {ctx.parent.id})'
    return "This is a top-level task. The user reviews your proposals."


def _description_block(ctx: TaskContext) -> str:
    return f"Description: {ctx.task.description}" if ctx.task.description else ""


def _context_block(ctx: TaskContext) -> str:
    """Include denial feedback and existing children for re-planning."""
    parts = []

    denied = find_denied_proposals(ctx)
    if denied:
        latest = max(denied, key=lambda c: c.created_at)
        parts.append(
            f"Your previous proposal was DENIED:\n"
            f"  {latest.text[:500]}\n"
            f"  Feedback: {latest.proposal_feedback or '(none)'}\n"
            f"Address this feedback."
        )

    if ctx.children:
        lines = ["Existing subtasks:"]
        for child in ctx.children:
            ai = child.props.get("aiStatus", "?")
            lines.append(f"  - {child.title} (status: {child.status}, aiStatus: {ai}, ID: {child.id})")
        lines.append("You can close obsolete ones, create new ones, or keep working ones.")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _subtasks_block(ctx: TaskContext) -> str:
    if not ctx.children:
        return "(no subtasks)"
    lines = []
    for child in ctx.children:
        ai = child.props.get("aiStatus", "?")
        lines.append(f"- {child.title} (status: {child.status}, aiStatus: {ai}, ID: {child.id})")
    return "\n".join(lines)


def _attention_block(ctx: TaskContext) -> str:
    lines = []

    # Pending proposals on children
    for child, proposal in find_pending_child_proposals(ctx):
        lines.append(f"- [{child.title}] PROPOSAL (id: {proposal.id}): {proposal.text[:300]}")

    # Children completed but not closed
    for child in ctx.children:
        if child.status != "CLOSED" and child.props.get("aiStatus", "") in _COMPLETED:
            already_listed = any(child.id == c.id for c, _ in find_pending_child_proposals(ctx))
            if not already_listed:
                child_comments = ctx.children_comments.get(child.id, [])
                last = child_comments[-1].text[:200] if child_comments else "no details"
                lines.append(f"- [{child.title}] COMPLETED — review and close_subtask(subtask_id={child.id}): {last}")

    # All closed
    if ctx.children and all(c.status == "CLOSED" for c in ctx.children):
        lines.append("- ALL SUBTASKS CLOSED — call submit_proof with a summary of all deliverables.")

    return "\n".join(lines) if lines else "(nothing needs attention)"


def _approved_plan(ctx: TaskContext) -> str:
    # Only consider approvals after the latest denial
    denied = find_denied_proposals(ctx)
    cutoff = max((c.created_at for c in denied), default=0)
    approved = [c for c in find_approved_proposals(ctx) if c.created_at > cutoff]
    if approved:
        return max(approved, key=lambda c: c.created_at).text
    return "(no approved plan found)"


# ---------------------------------------------------------------------------
# Algorithm
# ---------------------------------------------------------------------------

class SDLC(Algorithm):
    name = "sdlc"

    def initialize(self, ctx: TaskContext) -> PropsUpdate | None:
        updates: dict = {}

        # New task
        if not ctx.task.props.get("aiStatus"):
            updates["aiStatus"] = "plan"
            updates["algorithm"] = self.name

        # Inherit algorithm from parent
        if ctx.parent:
            parent_algo = ctx.parent.props.get("algorithm", "simple_answer")
            child_algo = ctx.task.props.get("algorithm", "simple_answer")
            if child_algo != self.name and parent_algo == self.name:
                updates["algorithm"] = self.name

        # Auto-fix: has children, in plan, no pending proposals, no recent denial → manage
        status = updates.get("aiStatus", ctx.task.props.get("aiStatus", "plan"))
        if ctx.children and status == "plan":
            has_pending = any(
                c.comment_type == "PROPOSAL" and c.proposal_status == "PENDING"
                for c in ctx.comments
            )
            has_recent_denial = False
            own = [c for c in ctx.comments if c.comment_type == "PROPOSAL" and _is_own_proposal(c, ctx)]
            if own:
                has_recent_denial = max(own, key=lambda c: c.created_at).proposal_status == "DENIED"

            if not has_pending and not has_recent_denial:
                updates["aiStatus"] = "manage"

        return PropsUpdate(self_props=updates) if updates else None

    def evaluate(self, ctx: TaskContext, is_running: bool) -> SpawnPlan | None:
        if is_running:
            return None

        status = ctx.task.props.get("aiStatus", "plan")

        if status == "plan":
            if find_pending_proposals(ctx):
                return None
            if _has_fresh_approval(ctx):
                return self._execute(ctx)
            return self._plan(ctx)

        if status == "execute":
            return self._execute(ctx)

        if status == "manage":
            return self._manage(ctx)

        if status == "done":
            if latest_proposal_denied(ctx):
                return self._reset_to_plan(ctx)
            return None

        if status == "awaiting_input":
            if has_proposal_resolved(ctx) or has_new_user_reply(ctx):
                resume = ctx.task.props.get("resumeState", "plan")
                if resume == "manage":
                    return self._manage(ctx)
                return self._plan(ctx)
            return None

        return None

    # -- Plan --------------------------------------------------------------

    def _plan(self, ctx: TaskContext) -> SpawnPlan:
        prompt = _PLAN_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            context_block=_context_block(ctx),
            task_id=ctx.task.id,
        )
        return SpawnPlan(
            prompt=prompt,
            tools=_plan_tools(),
            on_complete=_bump,
            metadata={"algo_tools": ["propose_plan", "request_clarification"]},
        )

    # -- Execute -----------------------------------------------------------

    def _execute(self, ctx: TaskContext) -> SpawnPlan:
        prompt = _EXECUTE_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            approved_plan=_approved_plan(ctx),
            task_id=ctx.task.id,
        )

        def on_executed(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            current = ctx.task.props.get("aiStatus")
            if current in ("execute", "plan"):
                if ctx.children:
                    return PropsUpdate(self_props={"aiStatus": "manage", "runCount": run_count})
                # Check if proof was submitted by the executor
                if current != "done":
                    return PropsUpdate(self_props={"aiStatus": "done", "runCount": run_count})
            return PropsUpdate(self_props={"runCount": run_count})

        return SpawnPlan(
            prompt=prompt,
            tools=_execute_tools(),
            on_complete=on_executed,
            metadata={"algo_tools": [
                "mark_as_planned", "mark_as_worker_ready",
                "submit_proof", "request_clarification",
            ]},
        )

    # -- Manage ------------------------------------------------------------

    def _manage(self, ctx: TaskContext) -> SpawnPlan | None:
        pending = find_pending_child_proposals(ctx)
        all_closed = all(c.status == "CLOSED" for c in ctx.children) if ctx.children else False
        completed = [c for c in ctx.children
                     if c.status != "CLOSED" and c.props.get("aiStatus", "") in _COMPLETED]

        if not pending and not completed and not all_closed:
            return None

        prompt = _MANAGE_PROMPT.format(
            title=ctx.task.title,
            parent_block=_parent_block(ctx),
            subtasks_block=_subtasks_block(ctx),
            attention_block=_attention_block(ctx),
            task_id=ctx.task.id,
        )

        def on_managed(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            all_done = all(c.status == "CLOSED" for c in ctx.children) if ctx.children else False
            if all_done and ctx.task.props.get("aiStatus") == "manage":
                return PropsUpdate(self_props={"aiStatus": "done", "runCount": run_count})
            return PropsUpdate(self_props={"runCount": run_count})

        return SpawnPlan(
            prompt=prompt,
            tools=_manage_tools(),
            on_complete=on_managed,
            metadata={"algo_tools": [
                "approve_child_proposal", "deny_child_proposal",
                "close_subtask", "request_rework",
                "submit_proof", "request_clarification",
            ]},
        )

    # -- Helpers -----------------------------------------------------------

    def _reset_to_plan(self, ctx: TaskContext) -> SpawnPlan:
        plan = self._plan(ctx)
        original = plan.on_complete
        def on_replan(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            result = original(ctx, result_text)
            props = result.self_props if result else {}
            props["aiStatus"] = "plan"
            return PropsUpdate(self_props=props)
        plan.on_complete = on_replan
        return plan


def _has_fresh_approval(ctx: TaskContext) -> bool:
    """Check for approved proposals newer than the latest denial."""
    denied = find_denied_proposals(ctx)
    cutoff = max((c.created_at for c in denied), default=0)
    return any(c.created_at > cutoff for c in find_approved_proposals(ctx))


def _bump(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
    return PropsUpdate(self_props={"runCount": ctx.task.props.get("runCount", 0) + 1})
