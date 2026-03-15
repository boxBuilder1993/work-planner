"""Core processing logic for the AI poller.

Two modes of operation:
1. **Hierarchy mode** (ai_enabled tasks): Detects worker/manager roles, spawns
   autonomous agents that communicate via proposals and the MCP tool layer.
2. **Legacy mode** (@ai comments): Responds to @ai mentions in comment threads
   as a simple assistant (backward compatible).
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

from api_client import ApiClient
from config import Config
from hierarchy import (
    detect_role,
    get_approved_proposals_for_task,
    get_pending_proposals_for_task,
    has_unreviewed_child_proposals,
    is_new_unprocessed_task,
)
from knowledge import KnowledgeBase, KnowledgeBaseFactory
from models import AIState, CommentEntity, TaskEntity
from spawner import AgentSpawner
from task_tools import create_workplanner_mcp_server, set_api_client
from workspace import WorkspaceManager

logger = logging.getLogger(__name__)

AI_STATE_FILE = Path(__file__).parent / "ai_state.json"


# ---------------------------------------------------------------------------
# AI state persistence
# ---------------------------------------------------------------------------

def _load_ai_state() -> AIState:
    try:
        if AI_STATE_FILE.exists():
            return AIState.model_validate_json(AI_STATE_FILE.read_text())
    except Exception:
        logger.warning("AI state corrupted, starting fresh")
    return AIState()


def _save_ai_state(state: AIState) -> None:
    AI_STATE_FILE.write_text(state.model_dump_json())


# ---------------------------------------------------------------------------
# Legacy @ai comment processing (for tasks without ai_enabled)
# ---------------------------------------------------------------------------

_LEGACY_PROMPT = """\
You are a concise AI assistant embedded in a task management app called WorkPlanner.
You are responding inside a comment thread on a task.

Guidelines:
- You can read AND write tasks and comments using the provided tools.
- Use read tools (get_task, get_subtasks, get_parent_chain, get_task_comments) to look up context.
- Use write tools (create_task, update_task, delete_task, add_comment) to make changes when the user asks.
- Use run_command to execute shell commands when the user asks.
- When creating subtasks, set the parent_id to the current task's ID.
- When marking a task done, set status to "CLOSED".
- Keep responses short and suitable for a comment thread (1-3 paragraphs max).
- Format as plain text — no markdown headers or bullet-heavy formatting.
- After making changes, briefly confirm what you did.
- Be helpful, direct, and actionable.
"""


def _is_ai_trigger(text: str) -> bool:
    return "@ai" in text.lower()


def _is_ai_response(text: str) -> bool:
    return text.startswith("[AI] ")


async def _process_legacy_comment(
    api: ApiClient,
    task: TaskEntity,
    comment: CommentEntity,
) -> str:
    """Run the Claude Agent SDK for a single @ai comment (legacy mode)."""
    set_api_client(api)
    mcp_server = create_workplanner_mcp_server()

    task_context = f"Task: {task.title}\nStatus: {task.status}, Priority: {task.priority}\n"
    if task.description:
        task_context += f"Description: {task.description}\n"

    prompt = (
        f"Context:\n{task_context}\n"
        f"The user wrote this comment on task {task.id}:\n"
        f'"{comment.text}"\n\n'
        f"Please respond to their message. Use tools to look up additional context if needed."
    )

    options = ClaudeAgentOptions(
        system_prompt=_LEGACY_PROMPT,
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


# ---------------------------------------------------------------------------
# Main poll cycle processor
# ---------------------------------------------------------------------------

class PollCycleProcessor:
    """Orchestrates one full poll cycle.

    Handles both hierarchy-mode (ai_enabled tasks) and legacy-mode (@ai comments).
    """

    def __init__(
        self,
        api: ApiClient,
        config: Config,
        spawner: AgentSpawner,
        workspace: WorkspaceManager,
        knowledge_factory: KnowledgeBaseFactory | None = None,
    ) -> None:
        self._api = api
        self._config = config
        self._spawner = spawner
        self._workspace = workspace
        self._knowledge_factory = knowledge_factory

    async def run_cycle(self) -> int:
        """Run one poll cycle. Returns the number of actions taken."""
        # Clean up stale agent runs
        self._spawner.cleanup_stale()

        # Fetch all tasks
        tasks = self._api.get_all_tasks()
        if not tasks:
            logger.info("No tasks found")
            return 0

        tasks_by_id = {t.id: t for t in tasks}

        # Fetch comments for all tasks
        all_comments = self._api.get_all_comments([t.id for t in tasks])
        comments_by_task: dict[str, list[CommentEntity]] = {}
        for c in all_comments:
            comments_by_task.setdefault(c.task_id, []).append(c)

        # Load AI state
        ai_state = _load_ai_state()

        actions = 0

        # --- Hierarchy mode: process ai_enabled tasks ---
        ai_tasks = [t for t in tasks if t.ai_enabled and t.status != "CLOSED"]
        if ai_tasks:
            actions += await self._process_hierarchy_tasks(
                ai_tasks, tasks, tasks_by_id, comments_by_task, ai_state,
            )

        # --- Legacy mode: process @ai comments on non-ai_enabled tasks ---
        actions += await self._process_legacy_comments(
            tasks, tasks_by_id, all_comments, ai_state,
        )

        _save_ai_state(ai_state)
        return actions

    async def _process_hierarchy_tasks(
        self,
        ai_tasks: list[TaskEntity],
        all_tasks: list[TaskEntity],
        tasks_by_id: dict[str, TaskEntity],
        comments_by_task: dict[str, list[CommentEntity]],
        ai_state: AIState,
    ) -> int:
        """Process ai_enabled tasks using the agent hierarchy system."""
        actions = 0
        all_comments_flat = [c for cs in comments_by_task.values() for c in cs]

        for task in ai_tasks:
            if not self._spawner.can_spawn():
                logger.info("Agent limit reached, deferring remaining tasks")
                break

            if self._spawner.is_running(task.id):
                continue

            task_comments = comments_by_task.get(task.id, [])
            has_children = any(t.parent_id == task.id for t in all_tasks)

            # 1. Skip tasks with pending proposals (waiting for approval)
            pending_proposals = get_pending_proposals_for_task(task, task_comments)
            if pending_proposals:
                continue

            # Resolve per-user knowledge base for this task
            task_knowledge: KnowledgeBase | None = None
            if self._knowledge_factory and task.user_id:
                task_knowledge = self._knowledge_factory.for_user(task.user_id)

            # 2. Approved proposal → re-spawn agent to continue work
            approved = get_approved_proposals_for_task(task, task_comments)
            if approved:
                role = detect_role(task, all_tasks)
                await self._spawner.spawn_agent(role, knowledge=task_knowledge)
                actions += 1
                continue

            # 3. New unprocessed task → spawn worker agent
            if is_new_unprocessed_task(task, task_comments, ai_state.processed_comment_ids):
                role = detect_role(task, all_tasks)
                await self._spawner.spawn_agent(role, knowledge=task_knowledge)
                ai_state.processed_comment_ids.add(task.id)
                actions += 1
                continue

            # 4. Manager: child tasks have unreviewed proposals → spawn manager to review
            if has_children and has_unreviewed_child_proposals(task, all_tasks, all_comments_flat):
                role = detect_role(task, all_tasks)
                await self._spawner.spawn_agent(role, knowledge=task_knowledge)
                actions += 1
                continue

        # Dequeue waiting tasks if slots available
        queued = [t for t in ai_tasks if t.status == "QUEUED"]
        for task in queued:
            if not self._spawner.can_spawn():
                break
            try:
                task_knowledge: KnowledgeBase | None = None
                if self._knowledge_factory and task.user_id:
                    task_knowledge = self._knowledge_factory.for_user(task.user_id)
                self._api.update_task(task.id, status="PENDING")
                role = detect_role(task, all_tasks)
                await self._spawner.spawn_agent(role, knowledge=task_knowledge)
                actions += 1
            except Exception:
                logger.exception("Failed to dequeue task %s", task.id)

        return actions

    async def _process_legacy_comments(
        self,
        tasks: list[TaskEntity],
        tasks_by_id: dict[str, TaskEntity],
        all_comments: list[CommentEntity],
        ai_state: AIState,
    ) -> int:
        """Process @ai comment triggers on non-ai_enabled tasks (legacy mode)."""
        pending: list[tuple[TaskEntity, CommentEntity]] = []

        for comment in all_comments:
            if comment.id in ai_state.processed_comment_ids:
                continue
            if _is_ai_response(comment.text):
                continue
            if not _is_ai_trigger(comment.text):
                continue

            task = tasks_by_id.get(comment.task_id)
            if task and not task.ai_enabled:
                pending.append((task, comment))

        if not pending:
            return 0

        logger.info("Found %d unprocessed @ai comment(s) (legacy mode)", len(pending))
        processed = 0

        for task, comment in pending:
            logger.info("Processing @ai comment %s on task '%s'", comment.id, task.title)
            try:
                response_text = await _process_legacy_comment(self._api, task, comment)
                self._api.create_comment(task.id, f"[AI] {response_text}")
                ai_state.processed_comment_ids.add(comment.id)
                processed += 1
            except Exception:
                logger.exception("Error processing comment %s", comment.id)

        return processed
