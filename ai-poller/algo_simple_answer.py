"""SimpleAnswer algorithm — single agent run, post the answer, done."""

from __future__ import annotations

from algo_tools import create_simple_answer_mcp
from algorithm import (
    Algorithm,
    TaskContext,
    SpawnPlan,
    PropsUpdate,
    format_comment_history,
    has_new_user_reply,
    has_proposal_resolved,
)

_PROMPT = """\
You are an AI assistant responding to a task in WorkPlanner.

Task: "{title}"
{description_block}

Previous activity:
{history}

Read the task and any comments. Answer the question or complete the request.

When you have your answer, call submit_answer with your response.
If you need clarification, call request_clarification with your question.\
"""


class SimpleAnswer(Algorithm):
    name = "simple_answer"

    def evaluate(self, ctx: TaskContext, is_running: bool) -> SpawnPlan | None:
        if is_running:
            return None

        status = ctx.task.props.get("aiStatus", "needs_planning")

        if status == "done":
            return None

        if status == "awaiting_input":
            if not has_proposal_resolved(ctx) and not has_new_user_reply(ctx):
                return None
            # Unblocked — re-run

        history = format_comment_history(ctx.comments)
        description_block = f"Description: {ctx.task.description}" if ctx.task.description else ""

        prompt = _PROMPT.format(
            title=ctx.task.title,
            description_block=description_block,
            history=history,
        )

        algo_mcp = create_simple_answer_mcp()

        def on_complete(ctx: TaskContext, result_text: str) -> PropsUpdate | None:
            # State transitions are handled by the agent via MCP tools.
            # Just bump runCount.
            run_count = ctx.task.props.get("runCount", 0) + 1
            return PropsUpdate(self_props={"runCount": run_count})

        return SpawnPlan(
            prompt=prompt,
            tools=({"algo": algo_mcp}, [
                "mcp__algo__*",
                "mcp__workplanner__get_task",
                "mcp__workplanner__get_subtasks",
                "mcp__workplanner__get_task_comments",
                "mcp__workplanner__get_parent_chain",
            ]),
            on_complete=on_complete,
        )
