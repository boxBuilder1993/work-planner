"""SimpleAnswer algorithm — single agent run, post the answer, done."""

from __future__ import annotations

from algorithm import (
    Algorithm,
    TaskContext,
    SpawnPlan,
    PropsUpdate,
    format_comment_history,
)

_PROMPT = """\
You are an AI assistant responding to a task in WorkPlanner.

Task: "{title}"
{description_block}

Previous activity:
{history}

Read the task and any comments. Answer the question or complete the request.
Be concise and direct. Your response will be posted as a comment automatically.\
"""


class SimpleAnswer(Algorithm):
    name = "simple_answer"

    def evaluate(self, ctx: TaskContext, is_running: bool) -> SpawnPlan | None:
        if is_running:
            return None

        status = ctx.task.props.get("aiStatus", "needs_planning")
        if status == "done":
            return None

        # Don't re-run if agent already posted a result
        agent_comments = [c for c in ctx.comments if c.created_by == ctx.task.id]
        if agent_comments and status != "needs_planning":
            return None

        history = format_comment_history(ctx.comments)
        description_block = f"Description: {ctx.task.description}" if ctx.task.description else ""

        prompt = _PROMPT.format(
            title=ctx.task.title,
            description_block=description_block,
            history=history,
        )

        def on_complete(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            run_count = ctx.task.props.get("runCount", 0) + 1
            return PropsUpdate(self_props={"aiStatus": "done", "runCount": run_count})

        return SpawnPlan(
            prompt=prompt,
            tools=({}, ["mcp__workplanner__get_task", "mcp__workplanner__get_subtasks",
                        "mcp__workplanner__get_task_comments", "mcp__workplanner__get_parent_chain"]),
            on_complete=on_complete,
        )
