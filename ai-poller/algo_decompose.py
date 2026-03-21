"""DecomposeAndDelegate algorithm — owner-based lifecycle.

States: needs_planning → plan_proposed → (in_progress | worker_ready)
        worker_ready → work_proposed → implementing → done
        in_progress → done
"""

from __future__ import annotations

import os

from algorithm import (
    Algorithm,
    TaskContext,
    SpawnPlan,
    PropsUpdate,
    format_comment_history,
    find_approved_proposals,
    find_pending_proposals,
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

IF this task needs to be broken down:
- Create HIGH-LEVEL subtasks using create_task (with ai_enabled=true, parent_id="{task_id}").
- Only create the IMMEDIATE next level — each subtask agent will decompose further if needed.
- Each subtask should have a clear title and description of what "done" looks like.
- Post a comment summarizing your decomposition plan.

IF this task is simple enough for one agent to implement:
- Post a comment explaining what you'll do and why it's small enough.

IF you need clarification from the user:
- Post a comment with your question. Do not create subtasks or proceed until answered.

Your agent task ID is: {task_id}
Always use this as agent_task_id when creating proposals, replies, or comments.\
"""

_WORKER_PROMPT = """\
You are the owner of task: "{title}"
{description_block}
{parent_block}

Previous activity:
{history}

You are in IMPLEMENTATION mode. Your approved plan:
{approved_plan}

Implement the work described above. Write code, run tests, open PRs as needed.

When your work is complete, submit proof of completion:
- Use submit_for_review on your PARENT task (task_id="{parent_id}") with concrete evidence.
- Include: command outputs, test results, PR links, file changes.
{close_instruction}
Your agent task ID is: {task_id}
Always use this as agent_task_id when creating proposals, replies, or comments.\
"""

_MANAGER_PROMPT = """\
You are the owner of task: "{title}"
{parent_block}

Your subtasks:
{subtasks_block}

Previous activity:
{history}

You are in MANAGEMENT mode. Your job is to:
1. Review proof-of-completion proposals from your subtask agents.
2. For each proposal, verify the evidence (read comments, check results).
3. If satisfied: approve the proposal AND close the subtask using update_task(task_id, status="CLOSED").
4. If not satisfied: deny the proposal with specific feedback.
5. If you need to REPLAN: create new subtasks or close obsolete ones.
6. When ALL subtasks are closed, submit your own proof to your parent:
   - Use submit_for_review on your parent task (task_id="{parent_id}").
   - Summarize what each subtask accomplished.
{close_instruction}
Use get_pending_proposals to find proposals awaiting your review.
Use get_task_comments(task_id=<subtask_id>) to read a subtask's full comment history.

Your agent task ID is: {task_id}
Always use this as agent_task_id when creating proposals, replies, or comments.\
"""


# ---------------------------------------------------------------------------
# Tool sets
# ---------------------------------------------------------------------------

def _planning_tools() -> tuple[dict, list[str]]:
    """Read-only code tools + workplanner + GitHub for exploration."""
    mcp_servers: dict = {}
    github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if github_token:
        mcp_servers["github"] = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": github_token},
        }
    return mcp_servers, [
        "mcp__workplanner__*",
        "mcp__github__*",
        "Read", "Glob", "Grep", "Bash",
    ]


def _worker_tools() -> tuple[dict, list[str]]:
    """Full code tools + git + GitHub."""
    mcp_servers: dict = {}
    mcp_servers["git"] = {
        "command": "npx",
        "args": ["-y", "git-mcp-server"],
    }
    github_token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if github_token:
        mcp_servers["github"] = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": github_token},
        }
    return mcp_servers, [
        "mcp__workplanner__*",
        "mcp__git__*",
        "mcp__github__*",
        "Read", "Write", "Edit", "Bash", "Glob", "Grep",
    ]


def _manager_tools() -> tuple[dict, list[str]]:
    """Workplanner tools only."""
    return {}, ["mcp__workplanner__*"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parent_block(ctx: TaskContext) -> str:
    if ctx.parent:
        return f'Your parent task is: "{ctx.parent.title}" (ID: {ctx.parent.id})'
    return "This is a top-level task (no parent). The user is your reviewer."


def _close_instruction(ctx: TaskContext) -> str:
    if ctx.parent is None:
        return (
            "\nThis is a top-level task. When your work is complete, post a summary "
            "comment with proof. Do NOT close this task — the user will close it."
        )
    return ""


def _description_block(ctx: TaskContext) -> str:
    return f"Description: {ctx.task.description}" if ctx.task.description else ""


def _subtasks_block(ctx: TaskContext) -> str:
    if not ctx.children:
        return "- (no subtasks)"
    lines = []
    for child in ctx.children:
        lines.append(f"- {child.title} (status: {child.status}, ID: {child.id})")
    return "\n".join(lines)


def _approved_plan_text(ctx: TaskContext) -> str:
    approved = find_approved_proposals(ctx)
    if approved:
        return approved[-1].text
    return "(no approved plan found)"


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
            return self._work(ctx)
        if status == "work_proposed":
            return self._handle_work_proposed(ctx)
        if status == "in_progress":
            return self._manage(ctx)
        if status == "awaiting_input":
            return self._handle_awaiting_input(ctx)
        # "done" → nothing to do
        return None

    # -- Planning ----------------------------------------------------------

    def _plan(self, ctx: TaskContext) -> SpawnPlan:
        history = format_comment_history(ctx.comments)
        prompt = _PLANNER_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            history=history,
            task_id=ctx.task.id,
        )

        def on_complete(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            # Check if subtasks were created during this run
            if ctx.children:
                return PropsUpdate(
                    self_props={"aiStatus": "in_progress", "runCount": run_count},
                    child_props={"algorithm": "decompose_and_delegate", "aiStatus": "needs_planning"},
                )
            # No subtasks — agent decided it's simple enough or asked a question
            # Check if agent posted a question (no subtasks, result mentions clarification)
            agent_comments = [c for c in ctx.comments if c.created_by == ctx.task.id]
            if agent_comments:
                last = agent_comments[-1].text.lower()
                if "?" in last or "clarif" in last or "question" in last:
                    return PropsUpdate(self_props={"aiStatus": "awaiting_input", "runCount": run_count})
            # Agent said it's implementable
            return PropsUpdate(self_props={"aiStatus": "worker_ready", "runCount": run_count})

        return SpawnPlan(
            prompt=prompt,
            tools=_planning_tools(),
            on_complete=on_complete,
        )

    def _handle_plan_proposed(self, ctx: TaskContext) -> SpawnPlan | None:
        # Check for approved proposals → proceed
        approved = find_approved_proposals(ctx)
        if approved:
            return self._plan(ctx)  # re-run planner to execute approved plan
        # Check for denied proposals → re-plan
        denied = [c for c in ctx.comments
                  if c.comment_type == "PROPOSAL" and c.proposal_status == "DENIED"
                  and c.created_by == ctx.task.id]
        if denied:
            # Reset to needs_planning so planner runs fresh with feedback
            return self._plan(ctx)
        # Still waiting for approval
        return None

    # -- Worker ------------------------------------------------------------

    def _work(self, ctx: TaskContext) -> SpawnPlan:
        history = format_comment_history(ctx.comments)
        parent_id = ctx.parent.id if ctx.parent else ctx.task.id
        prompt = _WORKER_PROMPT.format(
            title=ctx.task.title,
            description_block=_description_block(ctx),
            parent_block=_parent_block(ctx),
            history=history,
            approved_plan=_approved_plan_text(ctx),
            parent_id=parent_id,
            close_instruction=_close_instruction(ctx),
            task_id=ctx.task.id,
        )

        def on_complete(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            # Check if subtasks were created (worker decided to decompose)
            if ctx.children:
                return PropsUpdate(
                    self_props={"aiStatus": "in_progress", "runCount": run_count},
                    child_props={"algorithm": "decompose_and_delegate", "aiStatus": "needs_planning"},
                )
            # Check if proof was submitted (submit_for_review creates a PROPOSAL)
            proposals = find_pending_proposals(ctx)
            if proposals:
                return PropsUpdate(self_props={"aiStatus": "done", "runCount": run_count})
            # Worker ran but didn't submit proof — leave as worker_ready for retry
            return PropsUpdate(self_props={"runCount": run_count})

        return SpawnPlan(
            prompt=prompt,
            tools=_worker_tools(),
            on_complete=on_complete,
        )

    def _handle_work_proposed(self, ctx: TaskContext) -> SpawnPlan | None:
        approved = find_approved_proposals(ctx)
        if approved:
            return self._work(ctx)
        return None

    # -- Manager -----------------------------------------------------------

    def _manage(self, ctx: TaskContext) -> SpawnPlan | None:
        # Only spawn if there's something to review
        pending = find_pending_child_proposals(ctx)
        all_closed = all(c.status == "CLOSED" for c in ctx.children) if ctx.children else False

        if not pending and not all_closed:
            return None  # nothing to do yet

        history = format_comment_history(ctx.comments)
        parent_id = ctx.parent.id if ctx.parent else ctx.task.id
        prompt = _MANAGER_PROMPT.format(
            title=ctx.task.title,
            parent_block=_parent_block(ctx),
            subtasks_block=_subtasks_block(ctx),
            history=history,
            parent_id=parent_id,
            close_instruction=_close_instruction(ctx),
            task_id=ctx.task.id,
        )

        def on_complete(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            all_closed = all(c.status == "CLOSED" for c in ctx.children) if ctx.children else False
            if all_closed:
                return PropsUpdate(self_props={"aiStatus": "done", "runCount": run_count})
            return PropsUpdate(self_props={"runCount": run_count})

        return SpawnPlan(
            prompt=prompt,
            tools=_manager_tools(),
            on_complete=on_complete,
        )

    # -- Awaiting input ----------------------------------------------------

    def _handle_awaiting_input(self, ctx: TaskContext) -> SpawnPlan | None:
        if has_new_user_reply(ctx):
            # User replied — go back to planning with the new context
            return self._plan(ctx)
        return None
