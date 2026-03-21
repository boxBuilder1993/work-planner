"""DecomposeAndDelegate algorithm — owner-based lifecycle with explicit state tools.

The agent drives state transitions by calling MCP tools (mark_as_planned,
mark_as_worker_ready, submit_proof, etc.) rather than the system guessing
from side effects.

States: needs_planning → (in_progress | worker_ready) → done
"""

from __future__ import annotations

import os

from algo_tools import (
    create_dd_manager_mcp,
    create_dd_planner_mcp,
    create_dd_worker_mcp,
)
from algorithm import (
    Algorithm,
    TaskContext,
    SpawnPlan,
    PropsUpdate,
    format_comment_history,
    find_pending_child_proposals,
    has_new_user_reply,
)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PLANNER_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

Previous activity:
{history}

You are in PLANNING mode. Your job is to understand this task and decide how to handle it.

1. Explore the task — read repos, understand context, gather information.
2. Decide: can a single agent implement this, or does it need to be broken down?

IF this task needs multiple pieces of work:
- Create subtasks using create_task (with ai_enabled=true, parent_id="{task_id}").
- Only create the IMMEDIATE next level — keep subtasks broad and meaningful.
- Give each subtask a clear title and description of what "done" looks like.
- After creating subtasks, call mark_as_planned to move to management mode.

IF this task is simple enough for one agent to implement:
- Call mark_as_worker_ready to move to implementation mode.

IF you need clarification:
- Call request_clarification with your question. Do NOT proceed until answered.

Your task ID is: {task_id}\
"""

_WORKER_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

Previous activity:
{history}

You are in IMPLEMENTATION mode. Do the work described in this task.
Write code, run tests, open PRs as needed.

When your work is complete:
- If you have a parent task: call submit_proof with the parent_task_id and evidence.
- If this is a top-level task: call submit_summary with a summary of what you did.

Include concrete evidence: command outputs, test results, PR links, file changes.
If you get stuck, call request_clarification.

Your task ID is: {task_id}\
"""

_MANAGER_PROMPT = """\
You are the owner of task: "{title}"
{parent_block}

Your subtasks:
{subtasks_block}

Previous activity:
{history}

You are in MANAGEMENT mode. Review work from your subtask agents.

For each pending proposal (proof of completion):
- Read the evidence carefully using get_task_comments on the subtask.
- If the work is satisfactory: call close_subtask with the subtask_id.
- If the work needs fixes: call request_rework with feedback.

When ALL subtasks are closed:
- If you have a parent: call submit_proof with evidence of overall completion.
- If top-level: call submit_summary for the user to review.

If the plan needs to change, you can create new subtasks or close obsolete ones.

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
    mcp_servers: dict = {"algo": create_dd_planner_mcp()}
    github = _github_mcp()
    if github:
        mcp_servers["github"] = github
    return mcp_servers, [
        "mcp__algo__*",
        "mcp__workplanner__*",
        "mcp__github__*",
        "Read", "Glob", "Grep", "Bash",
    ]


def _worker_tools() -> tuple[dict, list[str]]:
    mcp_servers: dict = {"algo": create_dd_worker_mcp()}
    mcp_servers["git"] = {
        "command": "npx",
        "args": ["-y", "git-mcp-server"],
    }
    github = _github_mcp()
    if github:
        mcp_servers["github"] = github
    return mcp_servers, [
        "mcp__algo__*",
        "mcp__workplanner__*",
        "mcp__git__*",
        "mcp__github__*",
        "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    ]


def _manager_tools() -> tuple[dict, list[str]]:
    return {"algo": create_dd_manager_mcp()}, [
        "mcp__algo__*",
        "mcp__workplanner__get_task",
        "mcp__workplanner__get_subtasks",
        "mcp__workplanner__get_task_comments",
        "mcp__workplanner__get_pending_proposals",
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parent_block(ctx: TaskContext) -> str:
    if ctx.parent:
        return f'Your parent task is: "{ctx.parent.title}" (ID: {ctx.parent.id})'
    return "This is a top-level task (no parent). The user is your reviewer."


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


def _bump_run_count(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
    """Simple on_complete that just bumps runCount. State transitions are agent-driven."""
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
        if status == "worker_ready":
            return self._work(ctx)
        if status == "in_progress":
            return self._manage(ctx)
        if status == "awaiting_input":
            return self._handle_awaiting_input(ctx)
        # "done" → nothing to do
        return None

    def _plan(self, ctx: TaskContext) -> SpawnPlan:
        history = format_comment_history(ctx.comments)
        prompt = _PLANNER_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            history=history,
            task_id=ctx.task.id,
        )
        return SpawnPlan(
            prompt=prompt,
            tools=_planning_tools(),
            on_complete=_bump_run_count,
        )

    def _work(self, ctx: TaskContext) -> SpawnPlan:
        history = format_comment_history(ctx.comments)
        prompt = _WORKER_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            history=history,
            task_id=ctx.task.id,
        )
        return SpawnPlan(
            prompt=prompt,
            tools=_worker_tools(),
            on_complete=_bump_run_count,
        )

    def _manage(self, ctx: TaskContext) -> SpawnPlan | None:
        # Only spawn if there's something to review
        pending = find_pending_child_proposals(ctx)
        all_closed = all(c.status == "CLOSED" for c in ctx.children) if ctx.children else False

        if not pending and not all_closed:
            return None

        history = format_comment_history(ctx.comments)
        prompt = _MANAGER_PROMPT.format(
            title=ctx.task.title,
            parent_block=_parent_block(ctx),
            subtasks_block=_subtasks_block(ctx),
            history=history,
            task_id=ctx.task.id,
        )
        return SpawnPlan(
            prompt=prompt,
            tools=_manager_tools(),
            on_complete=_bump_run_count,
        )

    def _handle_awaiting_input(self, ctx: TaskContext) -> SpawnPlan | None:
        if has_new_user_reply(ctx):
            return self._plan(ctx)
        return None
