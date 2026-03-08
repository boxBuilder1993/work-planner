"""Core processing logic: find @ai comments, run Agent SDK, write responses.

Orchestrates one full download -> process -> upload cycle.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)

from models import TaskEntity, CommentEntity, AIState
from task_tools import set_data, create_workplanner_mcp_server
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
- You are READ-ONLY. You cannot create, modify, or delete tasks or comments.
- Use the provided tools to look up task details, subtasks, parent chain, and comment threads.
- Keep responses short and suitable for a comment thread (1-3 paragraphs max).
- Format as plain text — no markdown headers or bullet-heavy formatting.
- Be helpful, direct, and actionable.
- If you don't have enough context, say so briefly.
"""


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
) -> str:
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

    return result_text.strip() if result_text else "I wasn't able to generate a response."


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
        new_comments: list[CommentEntity] = []

        for task, comment in pending:
            logger.info(
                "Processing comment %s on task '%s' (%s)",
                comment.id, task.title, task.id,
            )
            try:
                response_text = await process_comment(task, comment, tasks, comments)
                now_ms = int(time.time() * 1000)
                ai_comment = CommentEntity(
                    id=str(uuid.uuid4()),
                    taskId=comment.task_id,
                    text=f"[AI] {response_text}",
                    createdAt=now_ms,
                    updatedAt=now_ms,
                )
                new_comments.append(ai_comment)
                ai_state.processed_comment_ids.add(comment.id)
                logger.info("Generated response for comment %s", comment.id)
            except Exception:
                logger.exception("Error processing comment %s", comment.id)

        if not new_comments:
            # Still save state so we don't reprocess failed comments forever
            self._save_ai_state(ai_state)
            return 0

        # Re-download latest comments to merge (avoid overwriting concurrent user data)
        latest_comments_plain = self._download_and_decrypt(DRIVE_FILE_COMMENTS)
        if latest_comments_plain:
            latest_comments = _parse_entities(latest_comments_plain, CommentEntity)
        else:
            latest_comments = []

        # Merge: add our new AI comments to the latest set
        merged = latest_comments + new_comments
        merged_bytes = _serialize_entities(merged)

        # Upload merged comments and updated AI state
        self._encrypt_and_upload(DRIVE_FILE_COMMENTS, merged_bytes)
        self._save_ai_state(ai_state)

        logger.info("Uploaded %d new AI comment(s)", len(new_comments))
        return len(new_comments)
