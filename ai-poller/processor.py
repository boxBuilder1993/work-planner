"""Core processing logic: find @ai comments, run Agent SDK, write responses.

Reads tasks and comments from the WorkPlanner backend API.  The agent can
read and write via MCP tools that also call the API directly.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)

from models import TaskEntity, CommentEntity, AIState
from task_tools import set_api_client, create_workplanner_mcp_server
from api_client import ApiClient

logger = logging.getLogger(__name__)

AI_STATE_FILE = Path(__file__).parent / "ai_state.json"

SYSTEM_PROMPT = """\
You are a concise AI assistant embedded in a task management app called WorkPlanner.
You are responding inside a comment thread on a task.

Guidelines:
- You can read AND write tasks and comments using the provided tools.
- Use read tools (get_task, get_subtasks, get_parent_chain, get_task_comments) to look up context.
- Use write tools (create_task, update_task, delete_task, add_comment) to make changes when the user asks.
- Use run_command to execute shell commands when the user asks. You can set a timeout or run in the background.
- When creating subtasks, set the parent_id to the current task's ID.
- When marking a task done, set status to "CLOSED".
- Keep responses short and suitable for a comment thread (1-3 paragraphs max).
- Format as plain text — no markdown headers or bullet-heavy formatting.
- After making changes, briefly confirm what you did.
- Be helpful, direct, and actionable.
- If you don't have enough context, say so briefly.
"""


def _is_ai_trigger(text: str) -> bool:
    return "@ai" in text.lower()


def _is_ai_response(text: str) -> bool:
    return text.startswith("[AI] ")


def _load_ai_state() -> AIState:
    try:
        if AI_STATE_FILE.exists():
            return AIState.model_validate_json(AI_STATE_FILE.read_text())
    except Exception:
        logger.warning("AI state corrupted, starting fresh")
    return AIState()


def _save_ai_state(state: AIState) -> None:
    AI_STATE_FILE.write_text(state.model_dump_json())


async def process_comment(
    api: ApiClient,
    task: TaskEntity,
    comment: CommentEntity,
) -> str:
    """Run the Claude Agent SDK to generate a response for a single @ai comment."""
    set_api_client(api)
    mcp_server = create_workplanner_mcp_server()

    task_context = (
        f"Task: {task.title}\n"
        f"Status: {task.status}, Priority: {task.priority}\n"
    )
    if task.description:
        task_context += f"Description: {task.description}\n"

    prompt = (
        f"Context:\n{task_context}\n"
        f"The user wrote this comment on task {task.id}:\n"
        f'"{comment.text}"\n\n'
        f"Please respond to their message. Use tools to look up additional context if needed."
    )

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"workplanner": mcp_server},
        allowed_tools=["mcp__workplanner__*"],
        max_turns=5,
        model="claude-sonnet-4-6",
        env={"ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "")},
    )

    result_text = ""
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, ResultMessage) and message.subtype == "success":
                result_text = message.result

    return result_text.strip() if result_text else "I wasn't able to generate a response."


class PollCycleProcessor:
    """Orchestrates one full poll cycle using the backend API."""

    def __init__(self, api: ApiClient) -> None:
        self._api = api

    async def run_cycle(self) -> int:
        """Run one poll cycle. Returns the number of comments processed."""
        # Fetch all tasks
        tasks = self._api.get_all_tasks()
        if not tasks:
            logger.info("No tasks found")
            return 0

        tasks_by_id = {t.id: t for t in tasks}

        # Fetch comments for all tasks
        comments = self._api.get_all_comments([t.id for t in tasks])

        # Load AI state
        ai_state = _load_ai_state()

        # Find unprocessed @ai comments
        pending: list[tuple[TaskEntity, CommentEntity]] = []
        for comment in comments:
            if comment.id in ai_state.processed_comment_ids:
                continue
            if _is_ai_response(comment.text):
                continue
            if _is_ai_trigger(comment.text):
                task = tasks_by_id.get(comment.task_id)
                if task:
                    pending.append((task, comment))

        if not pending:
            logger.info("No unprocessed @ai comments found")
            return 0

        logger.info("Found %d unprocessed @ai comment(s)", len(pending))
        processed_count = 0

        for task, comment in pending:
            logger.info(
                "Processing comment %s on task '%s' (%s)",
                comment.id, task.title, task.id,
            )
            try:
                response_text = await process_comment(self._api, task, comment)

                # Post the AI response as a new comment
                self._api.create_comment(task.id, f"[AI] {response_text}")

                ai_state.processed_comment_ids.add(comment.id)
                processed_count += 1
                logger.info("Generated response for comment %s", comment.id)
            except Exception:
                logger.exception("Error processing comment %s", comment.id)

        _save_ai_state(ai_state)
        return processed_count
