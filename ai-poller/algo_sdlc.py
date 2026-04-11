"""SDLC Algorithm — Propose-Approve-Execute loop.

3 states: propose, execute, manage (+ awaiting_input)

Every action is proposed, approved by parent, then executed.
The agent reads the SDLC spec to understand its role.
The debate layer handles quality automatically.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

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
    RuntimeRecommendation,
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
# Load spec
# ---------------------------------------------------------------------------

_SPEC = (Path(__file__).parent / "ALGO_SDLC_SPEC.md").read_text()

# ---------------------------------------------------------------------------
# Completed statuses for manager review
# ---------------------------------------------------------------------------

_COMPLETED = frozenset({"done", "proof_submitted", "complete"})

_STRONG_MODELS = [
    RuntimeRecommendation(runtime="codex", model="gpt-5-codex"),
    RuntimeRecommendation(runtime="claude", model="claude-sonnet-4-6"),
]

_CHEAP_MODELS = [
    RuntimeRecommendation(runtime="codex", model="gpt-5-codex-mini"),
    RuntimeRecommendation(runtime="claude", model="claude-sonnet-4-6"),
]


def _with_recommendations(plan: SpawnPlan, recommendations: list[RuntimeRecommendation]) -> SpawnPlan:
    if recommendations:
        plan.runtime = recommendations[0].runtime
        plan.model = recommendations[0].model
        plan.fallbacks = recommendations[1:]
    return plan


def _normalize_status(status: str) -> str:
    """Normalize persisted legacy aiStatus values into SDLC phases."""
    if status in ("planning", "needs_planning", "plan", "plan_proposed", "work_proposed", "worker_ready", "working", "todo"):
        return "propose"
    if status in ("plan_approved", "work_approved", "implementing", "execute"):
        return "execute"
    if status in ("in_progress", "managing", "manage"):
        return "manage"
    if status in ("proof_submitted", "complete", "done"):
        return "done"
    return status

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PROPOSE_PROMPT = """\
{spec}

---

You are the owner of task: "{title}"
{description_block}
{parent_block}

{context_block}

Previous activity:
{history}

Assess the current state and propose your next action.
Call propose_plan with a coherent batch of related actions that together accomplish one meaningful goal.
Do not create a proposal for a trivial one-step action by itself when it can be grouped with closely related discovery or implementation steps.
If you need clarification, call request_clarification.

Your task ID is: {task_id}\
"""

_EXECUTE_PROMPT = """\
{spec}

---

You are the owner of task: "{title}"
{description_block}
{parent_block}

Approved action:
{approved_action}

Execute exactly what was approved. Do not deviate.

After executing, assess whether more work remains:
- If you created subtasks: call mark_as_planned (you'll manage them next).
- If all work for this task is complete: call submit_proof with evidence.
- If more actions are needed: do nothing — you'll propose the next one.

Store decisions in the knowledge base via store_knowledge.

Your task ID is: {task_id}\
"""

_MANAGE_PROMPT = """\
{spec}

---

You are the manager of task: "{title}"
{parent_block}

Subtasks:
{subtasks_block}

Items needing attention:
{attention_block}

Previous activity:
{history}

Review your children's proposals and take action.
When all subtasks are CLOSED, call submit_proof with a summary.
If you need to take your own action (merge, deploy, etc.), call propose_plan.

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


_WP = [
    "mcp__workplanner__get_task",
    "mcp__workplanner__get_subtasks",
    "mcp__workplanner__get_task_comments",
    "mcp__workplanner__query_knowledge",
    "mcp__workplanner__store_knowledge",
    "mcp__workplanner__search_tasks",
]


def _propose_tools() -> tuple[dict, list[str]]:
    mcp: dict = {"algo": create_planning_mcp()}
    gh = _github_mcp()
    if gh:
        mcp["github"] = gh
    return mcp, ["mcp__algo__*", *_WP, "mcp__github__*", "Read", "Glob", "Grep", "Bash"]


def _execute_tools() -> tuple[dict, list[str]]:
    mcp: dict = {"algo": create_plan_execution_mcp()}
    mcp["git"] = {"command": "npx", "args": ["-y", "git-mcp-server"]}
    gh = _github_mcp()
    if gh:
        mcp["github"] = gh
    return mcp, [
        "mcp__algo__*", "mcp__workplanner__create_task", *_WP,
        "mcp__git__*", "mcp__github__*",
        "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    ]


def _manage_tools() -> tuple[dict, list[str]]:
    mcp: dict = {"algo": create_manager_mcp()}
    gh = _github_mcp()
    if gh:
        mcp["github"] = gh
    return mcp, ["mcp__algo__*", *_WP, "mcp__workplanner__get_subtasks", "mcp__github__*"]


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
    parts = []

    # Denial feedback
    denied = find_denied_proposals(ctx)
    if denied:
        latest = max(denied, key=lambda c: c.created_at)
        parts.append(
            f"Your previous proposal was DENIED:\n"
            f"  {latest.text[:500]}\n"
            f"  Feedback: {latest.proposal_feedback or '(none)'}\n"
            f"Propose something different that addresses this feedback."
        )

    # Children status
    if ctx.children:
        lines = ["Your subtasks:"]
        for child in ctx.children:
            ai = child.props.get("aiStatus", "?")
            lines.append(f"  - {child.title} (status: {child.status}, aiStatus: {ai}, ID: {child.id})")
        parts.append("\n".join(lines))

    return "\n\n".join(parts) if parts else ""


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

    for child, proposal in find_pending_child_proposals(ctx):
        lines.append(f"- [{child.title}] PROPOSAL (id: {proposal.id}): {proposal.text[:300]}")

    for child in ctx.children:
        if child.status != "CLOSED" and child.props.get("aiStatus", "") in _COMPLETED:
            already = any(child.id == c.id for c, _ in find_pending_child_proposals(ctx))
            if not already:
                child_comments = ctx.children_comments.get(child.id, [])
                last = child_comments[-1].text[:200] if child_comments else "no details"
                lines.append(f"- [{child.title}] COMPLETED — close_subtask(subtask_id={child.id}): {last}")

    if ctx.children and all(c.status == "CLOSED" for c in ctx.children):
        lines.append("- ALL SUBTASKS CLOSED — call submit_proof with summary of all deliverables.")

    return "\n".join(lines) if lines else "(nothing needs attention)"


def _approved_action(ctx: TaskContext) -> str:
    denied = find_denied_proposals(ctx)
    cutoff = max((c.created_at for c in denied), default=0)
    approved = [c for c in find_approved_proposals(ctx) if c.created_at > cutoff]
    if approved:
        return max(approved, key=lambda c: c.created_at).text
    return "(no approved action found)"


def _bump(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
    return PropsUpdate(self_props={"runCount": ctx.task.props.get("runCount", 0) + 1})


def _has_fresh_approval(ctx: TaskContext) -> bool:
    """Check for approved proposals newer than the latest denial AND not yet executed."""
    denied = find_denied_proposals(ctx)
    denial_cutoff = max((c.created_at for c in denied), default=0)
    executed_cutoff = ctx.task.props.get("lastExecutedApprovalTs", 0)
    cutoff = max(denial_cutoff, executed_cutoff)
    return any(c.created_at > cutoff for c in find_approved_proposals(ctx))


# ---------------------------------------------------------------------------
# Algorithm
# ---------------------------------------------------------------------------

class SDLC(Algorithm):
    name = "sdlc"

    def initialize(self, ctx: TaskContext) -> PropsUpdate | None:
        return None

    def _old_initialize(self, ctx: TaskContext) -> PropsUpdate | None:
        """Disabled — kept for reference."""
        updates: dict = {}

        current_status = ctx.task.props.get("aiStatus", "")
        if not current_status:
            updates["aiStatus"] = "propose"
            updates["algorithm"] = self.name
        elif current_status in ("planning", "needs_planning", "plan"):
            updates["aiStatus"] = "propose"

        if ctx.parent:
            parent_algo = ctx.parent.props.get("algorithm", "simple_answer")
            child_algo = ctx.task.props.get("algorithm", "simple_answer")
            if child_algo != self.name and parent_algo == self.name:
                updates["algorithm"] = self.name

        # Auto-fix: has children, in propose, no pending, no recent denial → manage
        status = updates.get("aiStatus", ctx.task.props.get("aiStatus", "propose"))
        if ctx.children and status == "propose":
            has_pending = any(
                c.comment_type == "PROPOSAL" and c.proposal_status == "PENDING"
                for c in ctx.comments
            )
            own = [c for c in ctx.comments if c.comment_type == "PROPOSAL" and _is_own_proposal(c, ctx)]
            has_recent_denial = own and max(own, key=lambda c: c.created_at).proposal_status == "DENIED"

            if not has_pending and not has_recent_denial:
                updates["aiStatus"] = "manage"

        return PropsUpdate(self_props=updates) if updates else None

    def evaluate(self, ctx: TaskContext, is_running: bool) -> SpawnPlan | None:
        logger.info("Task '%s': SDLC algorithm is disabled, skipping", ctx.task.title)
        return None

    def _old_evaluate(self, ctx: TaskContext, is_running: bool) -> SpawnPlan | None:
        if is_running:
            return None

        status = _normalize_status(ctx.task.props.get("aiStatus", "propose"))

        # The core loop
        if status == "propose":
            if find_pending_proposals(ctx):
                return None                         # waiting for approval
            if _has_fresh_approval(ctx):
                return self._execute(ctx)           # approved → do it
            return self._propose(ctx)               # propose next action

        if status == "execute":
            return self._execute(ctx)

        if status == "manage":
            # User comment on this task → re-propose (user wants something changed)
            if has_new_user_reply(ctx):
                return self._propose(ctx)
            return self._manage(ctx)

        if status == "done":
            if latest_proposal_denied(ctx):
                return self._reset_to_propose(ctx)  # denied → re-propose
            if has_new_user_reply(ctx):
                return self._reset_to_propose(ctx)  # user commented → re-assess
            return None                             # waiting for parent to close

        if status == "awaiting_input":
            if has_proposal_resolved(ctx) or has_new_user_reply(ctx):
                resume = _normalize_status(ctx.task.props.get("resumeState", "propose"))
                if resume == "awaiting_input":
                    resume = "propose"
                if resume == "manage":
                    return self._manage(ctx)
                if resume == "execute":
                    return self._execute(ctx)
                return self._propose(ctx)
            return None

        return None

    # -- Propose -----------------------------------------------------------

    def _propose(self, ctx: TaskContext) -> SpawnPlan:
        history = format_comment_history(ctx.comments)
        prompt = _PROPOSE_PROMPT.format(
            spec=_SPEC,
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            context_block=_context_block(ctx),
            history=history,
            task_id=ctx.task.id,
        )
        return _with_recommendations(SpawnPlan(
            prompt=prompt,
            tools=_propose_tools(),
            on_complete=_bump,
            metadata={"algo_tools": ["propose_plan", "request_clarification"]},
        ), _STRONG_MODELS)

    # -- Execute -----------------------------------------------------------

    def _execute(self, ctx: TaskContext) -> SpawnPlan:
        prompt = _EXECUTE_PROMPT.format(
            spec=_SPEC,
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            approved_action=_approved_action(ctx),
            task_id=ctx.task.id,
        )

        is_top_level = ctx.task.parent_id is None

        # Track which approval we're executing so we don't re-execute it
        approved = _approved_action(ctx)
        approved_ts = 0
        denied = find_denied_proposals(ctx)
        cutoff = max((c.created_at for c in denied), default=0)
        fresh = [c for c in find_approved_proposals(ctx) if c.created_at > cutoff]
        if fresh:
            approved_ts = max(c.created_at for c in fresh)

        def on_executed(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            current = _normalize_status(ctx.task.props.get("aiStatus", ""))
            # Mark this approval as consumed
            props: dict = {"runCount": run_count, "lastExecutedApprovalTs": approved_ts}
            if current in ("execute", "propose"):
                if ctx.children:
                    props["aiStatus"] = "manage"
                    return PropsUpdate(self_props=props)
                if is_top_level and current != "done":
                    logger.info("Top-level task %s tried to implement directly — forcing back to propose", ctx.task.id)
                    props["aiStatus"] = "propose"
                    return PropsUpdate(self_props=props)
                if current != "done":
                    props["aiStatus"] = "propose"
                    return PropsUpdate(self_props=props)
            return PropsUpdate(self_props=props)

        return _with_recommendations(SpawnPlan(
            prompt=prompt,
            tools=_execute_tools(),
            on_complete=on_executed,
            metadata={"algo_tools": [
                "mark_as_planned", "mark_as_worker_ready",
                "submit_proof", "request_clarification",
            ]},
        ), _CHEAP_MODELS)

    # -- Manage ------------------------------------------------------------

    def _manage(self, ctx: TaskContext) -> SpawnPlan | None:
        pending = find_pending_child_proposals(ctx)
        all_closed = all(c.status == "CLOSED" for c in ctx.children) if ctx.children else False
        completed = [c for c in ctx.children
                     if c.status != "CLOSED" and c.props.get("aiStatus", "") in _COMPLETED]

        if not pending and not completed and not all_closed:
            return None

        history = format_comment_history(ctx.comments)
        prompt = _MANAGE_PROMPT.format(
            spec=_SPEC,
            title=ctx.task.title,
            parent_block=_parent_block(ctx),
            subtasks_block=_subtasks_block(ctx),
            attention_block=_attention_block(ctx),
            history=history,
            task_id=ctx.task.id,
        )

        def on_managed(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            all_done = all(c.status == "CLOSED" for c in ctx.children) if ctx.children else False
            if all_done and _normalize_status(ctx.task.props.get("aiStatus", "")) == "manage":
                return PropsUpdate(self_props={"aiStatus": "done", "runCount": run_count})
            return PropsUpdate(self_props={"runCount": run_count})

        return _with_recommendations(SpawnPlan(
            prompt=prompt,
            tools=_manage_tools(),
            on_complete=on_managed,
            metadata={"algo_tools": [
                "approve_child_proposal", "deny_child_proposal",
                "close_subtask", "request_rework",
                "submit_proof", "propose_plan", "request_clarification",
            ]},
        ), _STRONG_MODELS)

    # -- Helpers -----------------------------------------------------------

    def _reset_to_propose(self, ctx: TaskContext) -> SpawnPlan:
        plan = self._propose(ctx)
        original = plan.on_complete
        def on_reset(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            result = original(ctx, result_text)
            props = result.self_props if result else {}
            props["aiStatus"] = "propose"
            return PropsUpdate(self_props=props)
        plan.on_complete = on_reset
        return plan
