"""Chat-mention scanner — turns @ai mentions into WorkItems.

This used to be the full dispatcher (poll mention → call proxy → write reply
comment). After the WorkItems refactor (see docs/WORK_ITEMS_DESIGN.md) it's
a thinner layer: every mention becomes a WorkItem with a fully-rendered
prompt, and `work_item_handler` is responsible for actually invoking the AI
and producing the reply.

Flow per poll cycle:
  1. Fetch comments matching `@ai*` with `ai-comment-status IS NULL` from
     the backend's `/api/internal/comments?needs_ai_reply=true` endpoint.
  2. Deduplicate to at most one mention per task per cycle (oldest wins).
  3. For each mention:
     a. Resolve task, ancestor chain, thread, and `ai_context`.
     b. Parse the @ai-<persona> suffix, route to a persona file.
     c. Guard against ai-manager → ai-manager self-loops.
     d. Build the rendered prompt payload.
     e. Create (idempotently) a WorkItem with prompt_context = the
        rendered prompt + dispatch metadata.
     f. Mark the comment's props.ai-comment-status = "enqueued" and
        props.ai-work-item-id = the new WorkItem id.

Dispatch, retries, and reply-comment posting all live in
`work_item_handler.py`. This module produces no AI calls — it only enqueues.
"""

from __future__ import annotations

import logging
from typing import Any

from api_client import ApiClient
from chat_prompt import PromptPayload, build_prompt
from config import Config
from models import CommentEntity, TaskEntity
from persona_registry import (
    MENTION_RE,
    CompiledPersona,
    route_mention,
)

logger = logging.getLogger(__name__)


class ChatHandler:
    def __init__(self, api: ApiClient, config: Config) -> None:
        self._api = api
        self._config = config

    # ─── Public API ───────────────────────────────────────────────────────

    async def run_cycle(self) -> int:
        """One scan cycle. Returns number of WorkItems created (or
        idempotently re-found) this cycle."""
        try:
            candidates = self._api.list_comments_needing_ai_reply()
        except Exception:
            logger.exception("Failed to fetch chat candidates")
            return 0

        if not candidates:
            logger.info("chat: no pending @ai mentions")
            return 0

        deduped = self._pick_one_per_task(candidates)
        logger.info(
            "chat: %d candidate(s); enqueuing %d (one per task)",
            len(candidates),
            len(deduped),
        )

        enqueued = 0
        for mention in deduped:
            try:
                if await self._enqueue(mention):
                    enqueued += 1
            except Exception:
                logger.exception(
                    "chat: unhandled error enqueuing mention %s", mention.id
                )
        return enqueued

    # ─── Per-mention pipeline ─────────────────────────────────────────────

    async def _enqueue(self, mention: CommentEntity) -> bool:
        """Build prompt, create WorkItem, mark the comment. Returns True if a
        WorkItem was created (or already existed for this mention)."""

        # 1. Skip if this mention has already been enqueued (idempotency at
        #    the poller side; backend's unique partial index is the second
        #    line of defense).
        if mention.props.get("ai-work-item-id"):
            return False

        # 2. Resolve task and ancestor chain.
        task = self._api.get_task(mention.task_id)
        if not task:
            logger.warning(
                "chat: mention %s references unknown task %s",
                mention.id, mention.task_id,
            )
            return False

        ancestors: list[TaskEntity] = []
        cursor = task
        visited: set[str] = {task.id}
        while cursor.parent_id and cursor.parent_id not in visited:
            visited.add(cursor.parent_id)
            try:
                parent = self._api.get_task(cursor.parent_id)
            except Exception:
                logger.exception(
                    "chat: failed to fetch parent %s of task %s",
                    cursor.parent_id, cursor.id,
                )
                break
            if not parent:
                break
            ancestors.insert(0, parent)
            cursor = parent

        all_comments = self._api.list_comments(task.id)
        thread = [c for c in all_comments if c.id != mention.id]

        # 3. Route persona.
        persona = self._route_persona(mention.text)

        # 4. Guard against ai-manager self-loops. Manager is the orchestrator
        #    persona; if a manager reply mentions @ai-manager, we'd loop
        #    forever. Mark the comment as 'skipped' and move on.
        if mention.created_by == "ai-manager" and persona.name == "manager":
            logger.info(
                "chat: skipping ai-manager self-mention %s (persona=manager)",
                mention.id,
            )
            try:
                self._api.update_comment_props(
                    mention.id, {"ai-comment-status": "skipped"}
                )
            except Exception:
                logger.exception(
                    "chat: failed to mark self-mention %s skipped", mention.id
                )
            return False

        # 5. Build the rendered prompt.
        ai_context = task.props.get("ai_context") or {}
        payload = build_prompt(
            task=task,
            ancestors=ancestors,
            thread=thread,
            mention=mention,
            persona=persona,
            ai_context=ai_context,
        )

        # 6. Create the WorkItem (idempotent on triggering_comment_id).
        prompt_context = _payload_to_prompt_context(payload, persona)
        try:
            work_item = self._api.create_work_item(
                task_id=task.id,
                target_persona=persona.name,
                triggering_comment_id=mention.id,
                prompt_context=prompt_context,
            )
        except Exception:
            logger.exception(
                "chat: failed to create WorkItem for mention %s", mention.id
            )
            return False

        # 7. Mark the comment so subsequent poll cycles skip it.
        try:
            self._api.update_comment_props(mention.id, {
                "ai-comment-status": "enqueued",
                "ai-work-item-id": work_item.id,
                "ai-persona": persona.name,
                "ai-prompt-version": f"{persona.name}@{persona.version}",
            })
        except Exception:
            # The WorkItem already exists; the worst case here is the next
            # cycle picks the mention again and create_work_item returns the
            # existing WorkItem (idempotency). No corruption.
            logger.exception(
                "chat: failed to mark mention %s enqueued (work_item=%s)",
                mention.id, work_item.id,
            )

        logger.info(
            "chat: enqueued mention %s as WorkItem %s (persona=%s)",
            mention.id, work_item.id, persona.name,
        )
        return True

    # ─── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _pick_one_per_task(candidates: list[CommentEntity]) -> list[CommentEntity]:
        """Group by task_id; keep the oldest mention per task."""
        by_task: dict[str, CommentEntity] = {}
        for c in candidates:
            existing = by_task.get(c.task_id)
            if existing is None or c.created_at < existing.created_at:
                by_task[c.task_id] = c
        return sorted(by_task.values(), key=lambda c: c.created_at)

    @staticmethod
    def _route_persona(mention_text: str) -> CompiledPersona:
        m = MENTION_RE.search(mention_text)
        suffix = m.group(1).lower() if m and m.group(1) else None
        return route_mention(suffix)


def _payload_to_prompt_context(payload: PromptPayload, persona: CompiledPersona) -> dict[str, Any]:
    """Serialize the rendered prompt payload into the JSONB shape we persist
    on work_items.prompt_context."""
    return {
        "system": payload.system,
        "user": payload.user,
        "model": payload.model,
        "allowed_tools": list(payload.allowed_tools),
        "max_turns": getattr(persona, "max_turns", 20),
        "persona_name": persona.name,
        "persona_version": persona.version,
        # Fixer pass config — work_item_handler runs a second model call to
        # extract the canonical JSON schema from the persona's raw output.
        # Empty fixer_model disables the pass (strict-parse only, today's
        # behavior for personas that haven't opted in).
        "fixer_model": getattr(persona, "fixer_model", "") or "",
        "fixer_max_turns": getattr(persona, "fixer_max_turns", 50),
    }
