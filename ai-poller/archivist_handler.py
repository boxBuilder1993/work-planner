"""Archivist scanner — turns new comments into knowledge-base reviews.

Third stage of the chat cycle (after chat_handler + work_item_handler). Where
chat_handler reacts to `@ai` mentions, the archivist reacts to *every* new
comment: each one is a chance for the company knowledge base to drift out of
date, so the archivist reviews it and decides whether a card needs creating,
updating, or nothing at all.

Flow per cycle:
  1. Fetch comments the archivist hasn't reviewed yet
     (`/api/internal/comments?needs_archival=true`), capped at
     `config.archivist_batch` (oldest first). Migration 010 marks all
     pre-existing comments reviewed, so there is no historical backlog — only
     comments created after the archivist was introduced surface here.
  2. For each: resolve the task + ancestor chain + thread, build the archivist
     prompt, and create a WorkItem (target_persona="archivist",
     triggering_comment_id=None — a sweep-created item, per migration 007).
  3. Mark the comment's props.archivist-reviewed so it won't be picked again.

Dispatch (proxy call + fixer pass) is handled by work_item_handler, same as
any other WorkItem. The archivist's WorkItems are silent — work_item_handler
suppresses the reply comment for them (the output is knowledge-card changes,
recorded on the WorkItem for audit, not a thread reply).

The archivist never posts comments, so it never triggers itself.
"""

from __future__ import annotations

import logging
from typing import Any

from api_client import ApiClient
from archivist_prompt import build_archivist_prompt
from config import Config
from models import CommentEntity, TaskEntity
from persona_registry import load_persona

logger = logging.getLogger(__name__)

ARCHIVIST_PERSONA = "archivist"


class ArchivistHandler:
    def __init__(self, api: ApiClient, config: Config) -> None:
        self._api = api
        self._config = config

    # ─── Public API ───────────────────────────────────────────────────────

    async def run_cycle(self) -> int:
        """One scan cycle. Returns the number of archival WorkItems created."""
        try:
            candidates = self._api.list_comments_needing_archival(
                limit=self._config.archivist_batch
            )
        except Exception:
            logger.exception("archivist: failed to fetch comments needing archival")
            return 0

        if not candidates:
            return 0

        logger.info("archivist: %d comment(s) to review", len(candidates))

        created = 0
        for comment in candidates:
            try:
                if await self._enqueue(comment):
                    created += 1
            except Exception:
                logger.exception(
                    "archivist: unhandled error reviewing comment %s", comment.id
                )
        return created

    # ─── Per-comment pipeline ─────────────────────────────────────────────

    async def _enqueue(self, comment: CommentEntity) -> bool:
        """Build the archivist prompt, create a WorkItem, mark the comment
        reviewed. Returns True if a WorkItem was created."""

        # Idempotency at the poller side: once marked, the comment won't be
        # returned by the needs_archival query again. (Sweep-created
        # WorkItems carry no triggering_comment_id, so the backend's
        # comment-unique index doesn't apply — the flag is the guard.)
        if comment.props.get("archivist-reviewed"):
            return False

        task = self._api.get_task(comment.task_id)
        if not task:
            logger.warning(
                "archivist: comment %s references unknown task %s",
                comment.id, comment.task_id,
            )
            # Mark reviewed so we don't keep retrying a dangling comment.
            self._mark_reviewed(comment, work_item_id=None)
            return False

        ancestors = self._resolve_ancestors(task)
        thread = [c for c in self._api.list_comments(task.id) if c.id != comment.id]

        persona = load_persona(ARCHIVIST_PERSONA)
        ai_context = task.props.get("ai_context") or {}
        payload = build_archivist_prompt(
            task=task,
            ancestors=ancestors,
            thread=thread,
            trigger=comment,
            persona=persona,
            ai_context=ai_context,
        )

        prompt_context = _payload_to_prompt_context(payload, persona)
        try:
            # No triggering_comment_id: archivist items are sweep-created and
            # must not collide with an @ai-mention WorkItem on the same comment
            # (the idempotency index is on triggering_comment_id alone).
            work_item = self._api.create_work_item(
                task_id=task.id,
                target_persona=ARCHIVIST_PERSONA,
                triggering_comment_id=None,
                prompt_context=prompt_context,
            )
        except Exception:
            logger.exception(
                "archivist: failed to create WorkItem for comment %s", comment.id
            )
            return False

        # Mark AFTER create so a transient mark failure re-runs the review next
        # cycle rather than silently dropping it. A duplicate archivist run is
        # harmless — it searches existing cards and converges to no-op.
        self._mark_reviewed(comment, work_item_id=work_item.id)

        logger.info(
            "archivist: enqueued review of comment %s as WorkItem %s",
            comment.id, work_item.id,
        )
        return True

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _resolve_ancestors(self, task: TaskEntity) -> list[TaskEntity]:
        """Walk parent_id up to the root, root-first, excluding `task`."""
        ancestors: list[TaskEntity] = []
        cursor = task
        visited: set[str] = {task.id}
        while cursor.parent_id and cursor.parent_id not in visited:
            visited.add(cursor.parent_id)
            try:
                parent = self._api.get_task(cursor.parent_id)
            except Exception:
                logger.exception(
                    "archivist: failed to fetch parent %s of task %s",
                    cursor.parent_id, cursor.id,
                )
                break
            if not parent:
                break
            ancestors.insert(0, parent)
            cursor = parent
        return ancestors

    def _mark_reviewed(self, comment: CommentEntity, work_item_id: str | None) -> None:
        patch: dict[str, Any] = {"archivist-reviewed": True}
        if work_item_id:
            patch["archivist-work-item-id"] = work_item_id
        try:
            self._api.update_comment_props(comment.id, patch)
        except Exception:
            logger.exception(
                "archivist: failed to mark comment %s reviewed", comment.id
            )


def _payload_to_prompt_context(payload, persona) -> dict[str, Any]:
    """Serialize the archivist prompt into the work_items.prompt_context shape.

    Mirrors chat_handler._payload_to_prompt_context; the fixer always runs so
    the archivist can write its summary in prose.
    """
    return {
        "system": payload.system,
        "user": payload.user,
        "model": payload.model,
        "allowed_tools": list(payload.allowed_tools),
        "max_turns": getattr(persona, "max_turns", 20),
        "persona_name": persona.name,
        "persona_version": persona.version,
        "fixer_model": getattr(persona, "fixer_model", "") or "",
        "fixer_max_turns": getattr(persona, "fixer_max_turns", 50),
    }
