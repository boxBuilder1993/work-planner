"""Orchestrated algorithm.

Two roles per task:
  Orchestrator — reads all context, decides next step, never writes code.
  Worker       — executes specific instructions from orchestrator, reports back.

States: orchestrating | worker_running | done

The poller spawns the orchestrator whenever there is new activity on a task
(new comment, subtask change) or after a 15-minute idle timeout.
When the orchestrator dispatches a worker, the poller spawns the worker on the
next cycle. The worker reports completion via report_complete, which resets the
task back to orchestrating so the orchestrator can decide the next step.
"""

from __future__ import annotations

import logging
import os
import time

from algo_tools import create_orchestrator_mcp, create_orchestrated_worker_mcp
from algorithm import (
    Algorithm,
    TaskContext,
    SpawnPlan,
    PropsUpdate,
    format_comment_history,
)

logger = logging.getLogger(__name__)

_WORKER_TIMEOUT_MS = 15 * 60 * 1000   # reset worker if running > 15 min
_IDLE_RECHECK_MS  = 15 * 60 * 1000   # re-orchestrate even with no new activity

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_ORCHESTRATOR_PROMPT = """\
You are an orchestrator agent. Your only job is to decide the IMMEDIATE next \
step for a task and take exactly one action.

## What you can do
- Read code (Read, Glob, Grep) to understand context — you CANNOT write or \
edit files
- Create subtasks via create_subtask (when work is too vague or large for one \
worker)
- Dispatch a worker via dispatch_worker (when you know exactly what to do)
- Post a comment via add_comment (to ask the user a question or give a status \
update)
- Close a subtask via close_subtask (when the user asks you to, or when \
all evidence confirms it is done)
- Mark this task done via mark_orchestrated_done (when all work is complete)

## Decision rules
1. Too vague or large → create focused subtasks (each with aiEnabled=true, \
parentId=this task)
2. Know exactly what to do → dispatch_worker with specific instructions
3. Need the user's input → add_comment with your question, then stop
4. Worker just reported back → read its output, decide what comes next
5. All work done → mark_orchestrated_done

## dispatch_worker — only call when ALL of these are true
- You know the specific files, repos, or commands involved
- Scope is bounded (not "implement the whole feature")
- The worker can execute without guessing or asking questions

## Workers
Workers have full execution tools: write code, run commands, git, GitHub, open \
PRs. Give them enough context to work independently. They will call \
report_complete when done and their result will appear as a comment.

---

{context}

Query the knowledge base first if useful. Then decide and act.
"""

_WORKER_PROMPT = """\
You are a worker agent. Execute the instructions below precisely, then call \
report_complete with what you did and any evidence.

## Instructions from orchestrator
{instructions}

---

Task: "{title}"
{description_block}
Task ID: {task_id}

Recent activity:
{history}

## Rules
- Execute exactly what was instructed — do not go beyond scope
- If you get blocked, still call report_complete describing what you tried and \
where you were blocked
"""


# ---------------------------------------------------------------------------
# Helpers
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


def _build_context(ctx: TaskContext, recovery: bool = False) -> str:
    parts: list[str] = []

    parts.append(f'Task: "{ctx.task.title}"')
    if ctx.task.description:
        parts.append(f"Description: {ctx.task.description}")
    parts.append(f"Task ID: {ctx.task.id}")

    if ctx.ancestors:
        parts.append("Context chain (root → this task):")
        for anc in ctx.ancestors:
            line = f'  • "{anc.title}"'
            if anc.description:
                line += f': {anc.description}'
            parts.append(line)
    elif not ctx.parent:
        parts.append("This is a top-level task — the user reviews your output.")

    if ctx.children:
        parts.append("\nSubtasks:")
        for child in ctx.children:
            ai = child.props.get("aiStatus", "?")
            parts.append(
                f"  [{child.status}] {child.title} "
                f"— aiStatus: {ai} — id: {child.id}"
            )

    if recovery:
        parts.append(
            "\n⚠️  The previous worker timed out. Read the comment history to "
            "understand what happened, then decide the next step."
        )

    history = format_comment_history(ctx.comments)
    parts.append(f"\nComment history:\n{history}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Algorithm
# ---------------------------------------------------------------------------

class Orchestrated(Algorithm):
    name = "orchestrated"

    # -- Lifecycle -----------------------------------------------------------

    def initialize(self, ctx: TaskContext) -> PropsUpdate | None:
        if not ctx.task.props.get("aiStatus"):
            return PropsUpdate(self_props={
                "aiStatus": "orchestrating",
                "algorithm": self.name,
            })
        return None

    def evaluate(self, ctx: TaskContext, is_running: bool) -> SpawnPlan | None:
        if is_running:
            return None

        status = ctx.task.props.get("aiStatus", "orchestrating")

        if status == "done":
            return None

        if status == "worker_running":
            worker_started = ctx.task.props.get("workerStartedAt", 0)
            now_ms = int(time.time() * 1000)
            if now_ms - worker_started > _WORKER_TIMEOUT_MS:
                logger.warning(
                    "Task %s: worker timed out after 15 min — re-orchestrating",
                    ctx.task.id,
                )
                return self._orchestrate(ctx, recovery=True)
            return self._run_worker(ctx)

        # orchestrating — fire on new activity or idle timeout
        last_at = ctx.task.props.get("lastOrchestratedAt", 0)
        now_ms = int(time.time() * 1000)
        has_new = any(c.created_at > last_at for c in ctx.comments)
        overdue = (now_ms - last_at) > _IDLE_RECHECK_MS

        if has_new or overdue or not last_at:
            return self._orchestrate(ctx)

        return None

    # -- Orchestrator spawn --------------------------------------------------

    def _orchestrate(self, ctx: TaskContext, recovery: bool = False) -> SpawnPlan:
        context = _build_context(ctx, recovery=recovery)
        prompt = _ORCHESTRATOR_PROMPT.format(context=context)

        mcp: dict = {"algo": create_orchestrator_mcp()}
        gh = _github_mcp()
        if gh:
            mcp["github"] = gh

        allowed = [
            "mcp__algo__dispatch_worker",
            "mcp__algo__mark_orchestrated_done",
            "mcp__algo__close_subtask",
            "mcp__algo__create_subtask",
            "mcp__workplanner__get_task",
            "mcp__workplanner__get_subtasks",
            "mcp__workplanner__get_task_comments",
            "mcp__workplanner__add_comment",
            "mcp__workplanner__search_tasks",
            "mcp__github__*",
            "Read", "Glob", "Grep",
        ]

        def on_complete(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            now_ms = int(time.time() * 1000)
            # If orchestrator called dispatch_worker, aiStatus is now worker_running
            # (set by the tool). Just bump metadata.
            return PropsUpdate(self_props={
                "runCount": run_count,
                "lastOrchestratedAt": now_ms,
            })

        return SpawnPlan(
            prompt=prompt,
            tools=(mcp, allowed),
            on_complete=on_complete,
            is_orchestrator=True,
            metadata={"algo_tools": [
                "dispatch_worker", "mark_orchestrated_done", "close_subtask",
            ]},
        )

    # -- Worker spawn --------------------------------------------------------

    def _run_worker(self, ctx: TaskContext) -> SpawnPlan:
        instructions = ctx.task.props.get(
            "workerInstructions",
            "(no instructions stored — read the task and comment history)",
        )
        history = format_comment_history(ctx.comments)
        desc = f"Description: {ctx.task.description}" if ctx.task.description else ""

        prompt = _WORKER_PROMPT.format(
            instructions=instructions,
            title=ctx.task.title,
            description_block=desc,
            task_id=ctx.task.id,
            history=history,
        )

        mcp: dict = {"algo": create_orchestrated_worker_mcp()}
        mcp["git"] = {"command": "npx", "args": ["-y", "git-mcp-server"]}
        gh = _github_mcp()
        if gh:
            mcp["github"] = gh

        allowed = [
            "mcp__algo__report_complete",
            "mcp__workplanner__get_task",
            "mcp__workplanner__get_task_comments",
            "mcp__workplanner__add_comment",
            "mcp__git__*",
            "mcp__github__*",
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
        ]

        def on_complete(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            props: dict = {"runCount": run_count}
            # report_complete sets aiStatus → orchestrating via the tool.
            # Safety net: if worker crashed without calling the tool, reset it.
            if ctx.task.props.get("aiStatus") == "worker_running":
                props["aiStatus"] = "orchestrating"
                logger.warning(
                    "Task %s: worker finished but aiStatus still worker_running "
                    "— forcing back to orchestrating",
                    ctx.task.id,
                )
            return PropsUpdate(self_props=props)

        return SpawnPlan(
            prompt=prompt,
            tools=(mcp, allowed),
            on_complete=on_complete,
            metadata={"algo_tools": ["report_complete"]},
        )
