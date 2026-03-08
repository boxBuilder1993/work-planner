"""Core processing logic: find @ai comments, run Agent SDK, write responses.

Orchestrates one full download -> process -> upload cycle.  The agent can now
both read *and* write tasks/comments via MCP tools.  After all agent runs in a
cycle complete, mutations are merged with the latest Drive data and uploaded.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)

from models import TaskEntity, CommentEntity, AIState
from task_tools import (
    set_data,
    create_workplanner_mcp_server,
    get_dirty_flags,
    get_current_tasks,
    get_current_comments,
)
from drive_client import DriveClient
from encryption import encrypt, decrypt

logger = logging.getLogger(__name__)

DRIVE_FILE_TASKS = "workplanner_tasks.enc"
DRIVE_FILE_COMMENTS = "workplanner_comments.enc"
DRIVE_FILE_AI_STATE = "workplanner_ai_state.enc"

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


@dataclass
class AgentResult:
    """Result of a single agent run, including any mutations made."""

    response_text: str
    tasks_dirty: bool = False
    comments_dirty: bool = False
    tasks: list[TaskEntity] = field(default_factory=list)
    comments: list[CommentEntity] = field(default_factory=list)


def _is_ai_trigger(text: str) -> bool:
    """Check if a comment contains an @ai mention (case-insensitive)."""
    return "@ai" in text.lower()


def _is_ai_response(text: str) -> bool:
    """Check if a comment is an AI-generated response."""
    return text.startswith("[AI] ")


def _parse_entities(raw_json: bytes, model_cls):
    """Parse a JSON object keyed by ID (Record<string, T> format)."""
    data = json.loads(raw_json)
    return [model_cls.model_validate(item) for item in data.values()]


def _serialize_entities(entities, by_alias: bool = True) -> bytes:
    """Serialize entities to JSON object keyed by ID (Record<string, T> format)."""
    data = {e.id: e.model_dump(by_alias=by_alias) for e in entities}
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


async def process_comment(
    task: TaskEntity,
    comment: CommentEntity,
    all_tasks: list[TaskEntity],
    all_comments: list[CommentEntity],
) -> AgentResult:
    """Run the Claude Agent SDK to generate a response for a single @ai comment."""
    set_data(all_tasks, all_comments)
    mcp_server = create_workplanner_mcp_server()

    # Build the user prompt with task context
    task_context = (
        f"Task: {task.title}\n"
        f"Status: {task.status}, Priority: {task.priority}\n"
    )
    if task.description:
        task_context += f"Description: {task.description}\n"

    # Strip the @ai prefix to get the actual question
    question = comment.text
    for prefix in ["@ai ", "@AI ", "@Ai "]:
        if question.startswith(prefix):
            question = question[len(prefix):]
            break

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

    tasks_dirty, comments_dirty = get_dirty_flags()
    return AgentResult(
        response_text=result_text.strip() if result_text else "I wasn't able to generate a response.",
        tasks_dirty=tasks_dirty,
        comments_dirty=comments_dirty,
        tasks=get_current_tasks(),
        comments=get_current_comments(),
    )


class PollCycleProcessor:
    """Orchestrates one full poll cycle: download -> process -> upload."""

    def __init__(self, drive: DriveClient, key: bytes) -> None:
        self._drive = drive
        self._key = key

    def _download_and_decrypt(self, filename: str) -> bytes | None:
        """Download an encrypted file and decrypt it. Returns None if missing."""
        raw = self._drive.download_file_by_name(filename)
        if raw is None:
            return None
        return decrypt(raw, self._key)

    def _encrypt_and_upload(self, filename: str, data: bytes) -> None:
        """Encrypt data and upload to Drive."""
        encrypted = encrypt(data, self._key)
        self._drive.upload_or_update_file(filename, encrypted)

    def _load_ai_state(self) -> AIState:
        """Load AI state from Drive. Returns fresh state if missing or corrupted."""
        try:
            plain = self._download_and_decrypt(DRIVE_FILE_AI_STATE)
            if plain is None:
                return AIState()
            return AIState.model_validate_json(plain)
        except Exception:
            logger.warning("AI state corrupted or missing, starting fresh")
            return AIState()

    def _save_ai_state(self, state: AIState) -> None:
        """Save AI state to Drive."""
        data = state.model_dump_json().encode("utf-8")
        self._encrypt_and_upload(DRIVE_FILE_AI_STATE, data)

    @staticmethod
    def _merge_tasks(
        drive_tasks: list[TaskEntity],
        agent_tasks: list[TaskEntity],
    ) -> list[TaskEntity]:
        """Merge agent mutations into latest Drive tasks (agent-wins strategy).

        - New IDs from agent are added.
        - IDs present in agent but absent from Drive are kept (agent created them).
        - IDs present in Drive but absent from agent are removed (agent deleted them).
        - For IDs present in both, the agent version wins.
        """
        drive_map = {t.id: t for t in drive_tasks}
        agent_map = {t.id: t for t in agent_tasks}

        merged: dict[str, TaskEntity] = {}
        # Start with agent's view (includes creates, updates, and excludes deletes)
        all_ids = set(drive_map.keys()) | set(agent_map.keys())
        for tid in all_ids:
            if tid in agent_map:
                # Agent version wins (covers creates and updates)
                merged[tid] = agent_map[tid]
            # If tid only in drive_map and not in agent_map, agent deleted it — skip
        return list(merged.values())

    @staticmethod
    def _merge_comments(
        drive_comments: list[CommentEntity],
        agent_comments: list[CommentEntity],
    ) -> list[CommentEntity]:
        """Merge agent comments with latest Drive comments (union by ID, agent wins)."""
        merged: dict[str, CommentEntity] = {}
        for c in drive_comments:
            merged[c.id] = c
        for c in agent_comments:
            merged[c.id] = c  # agent version wins for duplicates
        return list(merged.values())

    async def run_cycle(self) -> int:
        """Run one poll cycle. Returns the number of comments processed."""
        # Download current data
        tasks_plain = self._download_and_decrypt(DRIVE_FILE_TASKS)
        comments_plain = self._download_and_decrypt(DRIVE_FILE_COMMENTS)

        if tasks_plain is None:
            logger.info("No tasks file found on Drive, skipping cycle")
            return 0

        tasks = _parse_entities(tasks_plain, TaskEntity)
        comments = _parse_entities(comments_plain, CommentEntity) if comments_plain else []
        tasks_by_id = {t.id: t for t in tasks}

        # Load AI state
        ai_state = self._load_ai_state()

        # Find unprocessed @ai comments
        pending = []
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
        new_ai_comments: list[CommentEntity] = []
        any_tasks_dirty = False
        any_comments_dirty = False

        # Track latest state across sequential agent runs so each sees prior mutations
        latest_tasks = list(tasks)
        latest_agent_comments = list(comments)

        for task, comment in pending:
            logger.info(
                "Processing comment %s on task '%s' (%s)",
                comment.id, task.title, task.id,
            )
            try:
                result = await process_comment(
                    task, comment, latest_tasks, latest_agent_comments,
                )

                # Track dirty flags across all runs
                any_tasks_dirty = any_tasks_dirty or result.tasks_dirty
                any_comments_dirty = any_comments_dirty or result.comments_dirty

                # Propagate mutations to next agent run
                latest_tasks = result.tasks
                latest_agent_comments = result.comments

                # Create the AI response comment
                now_ms = int(time.time() * 1000)
                ai_comment = CommentEntity(
                    id=str(uuid.uuid4()),
                    taskId=comment.task_id,
                    text=f"[AI] {result.response_text}",
                    createdAt=now_ms,
                    updatedAt=now_ms,
                )
                new_ai_comments.append(ai_comment)
                ai_state.processed_comment_ids.add(comment.id)
                logger.info("Generated response for comment %s", comment.id)
            except Exception:
                logger.exception("Error processing comment %s", comment.id)

        if not new_ai_comments and not any_tasks_dirty and not any_comments_dirty:
            # Still save state so we don't reprocess failed comments forever
            self._save_ai_state(ai_state)
            return 0

        # --- Upload task mutations ---
        if any_tasks_dirty:
            # Re-download latest tasks from Drive and merge with agent's version
            fresh_tasks_plain = self._download_and_decrypt(DRIVE_FILE_TASKS)
            fresh_tasks = (
                _parse_entities(fresh_tasks_plain, TaskEntity)
                if fresh_tasks_plain
                else []
            )
            merged_tasks = self._merge_tasks(fresh_tasks, latest_tasks)
            self._encrypt_and_upload(
                DRIVE_FILE_TASKS, _serialize_entities(merged_tasks),
            )
            logger.info("Uploaded merged tasks (%d total)", len(merged_tasks))

        # --- Upload comment mutations + AI response comments ---
        if any_comments_dirty or new_ai_comments:
            # Re-download latest comments from Drive and merge
            fresh_comments_plain = self._download_and_decrypt(DRIVE_FILE_COMMENTS)
            fresh_comments = (
                _parse_entities(fresh_comments_plain, CommentEntity)
                if fresh_comments_plain
                else []
            )
            merged_comments = self._merge_comments(fresh_comments, latest_agent_comments)
            # Append AI response comments (they're brand new, not in agent state)
            for aic in new_ai_comments:
                merged_comments.append(aic)
            self._encrypt_and_upload(
                DRIVE_FILE_COMMENTS, _serialize_entities(merged_comments),
            )
            logger.info(
                "Uploaded merged comments (%d total, %d new AI responses)",
                len(merged_comments), len(new_ai_comments),
            )

        self._save_ai_state(ai_state)
        logger.info("Uploaded %d new AI comment(s)", len(new_ai_comments))
        return len(new_ai_comments)
