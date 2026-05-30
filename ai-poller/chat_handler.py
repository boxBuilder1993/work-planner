"""Chat-mention dispatch handler.

Replaces the legacy algorithm dispatch when ENABLE_CHAT_HANDLER is set.

Flow per poll cycle:
  1. Fetch comments matching `@ai*` with `ai-comment-status IS NULL` from the
     backend's `/api/internal/comments?needs_ai_reply=true` endpoint.
  2. Deduplicate to at most one mention per task per cycle (oldest wins).
  3. For each mention:
     a. Resolve task, ancestor chain, thread, and `ai_context`.
     b. Parse the @ai-<persona> suffix, route to a persona file.
     c. Build the prompt payload (system + user + tool/model). The
        workspace path is owned by the proxy — it derives it from task_id.
     d. PATCH the mention with ai-comment-status="dispatched" (lock).
     e. POST /run to claude-proxy; poll /status until done or timeout.
     f. Validate the inner JSON; on success: post reply comment, merge
        context_update into task.props.ai_context, flip status to "replied",
        and stamp telemetry from proxy metadata.
     g. On failure: retry up to MAX_RETRIES, then mark "failed" with error.

See: docs/CHAT_DESIGN.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from api_client import ApiClient
from chat_prompt import PromptPayload, build_prompt
from config import Config
from models import CommentEntity, TaskEntity
from persona_registry import (
    DEFAULT_PERSONA_NAME,
    MENTION_RE,
    CompiledPersona,
    route_mention,
)

logger = logging.getLogger(__name__)


PROXY_POLL_INTERVAL_S = 5
PROXY_POLL_MAX_S = 600  # 10 minutes total per dispatch
MAX_RETRIES = 3


# ─── Dispatch outcome ─────────────────────────────────────────────────────


@dataclass
class DispatchOutcome:
    """Result of a single proxy round-trip (submit + poll)."""

    success: bool
    runtime: str = ""
    # Inner JSON the AI emitted: {reply_text, context_update}.
    reply_text: str = ""
    context_update: dict[str, Any] = field(default_factory=dict)
    # claude -p full envelope: duration_ms, total_cost_usd, stop_reason, usage, …
    metadata: dict[str, Any] = field(default_factory=dict)
    # Failure details (populated when success=False).
    error: str = ""
    error_code: str = ""


# ─── Chat handler ─────────────────────────────────────────────────────────


class ChatHandler:
    def __init__(self, api: ApiClient, config: Config) -> None:
        self._api = api
        self._config = config
        self._proxy_url = os.environ.get("CLAUDE_PROXY_URL", "http://localhost:8400")
        self._proxy_key = os.environ.get("CLAUDE_PROXY_KEY", "")

    # ─── Public API ───────────────────────────────────────────────────────

    async def run_cycle(self) -> int:
        """One poll cycle. Returns number of mentions handled."""
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
            "chat: %d candidate(s); processing %d (one per task)",
            len(candidates),
            len(deduped),
        )

        handled = 0
        for mention in deduped:
            try:
                await self._handle_mention(mention)
                handled += 1
            except Exception:
                logger.exception("chat: unhandled error processing mention %s", mention.id)
        return handled

    # ─── Per-mention pipeline ─────────────────────────────────────────────

    async def _handle_mention(self, mention: CommentEntity) -> None:
        # 1. Load context
        task = self._api.get_task(mention.task_id)
        if not task:
            logger.warning(
                "chat: mention %s references unknown task %s",
                mention.id,
                mention.task_id,
            )
            return

        # Walk parents via the internal /tasks/:id endpoint (which works with
        # the poller's API-key auth). The user-facing breadcrumbs endpoint
        # requires a JWT-scoped userID, which the internal auth doesn't supply.
        ancestors: list[TaskEntity] = []
        cursor = task
        visited: set[str] = {task.id}
        while cursor.parent_id and cursor.parent_id not in visited:
            visited.add(cursor.parent_id)
            try:
                parent = self._api.get_task(cursor.parent_id)
            except Exception:
                logger.exception("chat: failed to fetch parent %s of task %s", cursor.parent_id, cursor.id)
                break
            if not parent:
                break
            ancestors.insert(0, parent)
            cursor = parent

        all_comments = self._api.list_comments(task.id)
        thread = [c for c in all_comments if c.id != mention.id]

        # 2. Route persona + check for any in-flight dispatch on this task
        if self._task_has_dispatch_in_flight(all_comments, mention.id):
            logger.info(
                "chat: task %s has another mention in flight; skipping %s",
                task.id,
                mention.id,
            )
            return

        persona = self._route_persona(mention.text)

        # 2b. Manager is the only AI allowed to dispatch (orchestrator role).
        # The backend SQL already filters other AI authors out; here we guard
        # against manager mentioning manager (would self-loop forever).
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
                logger.exception("chat: failed to mark self-mention %s skipped", mention.id)
            return

        # 3. Build prompt. Workspace path is computed by the proxy from
        #    task.id + its own WORKSPACE_BASE, so we don't pass it here.
        ai_context = task.props.get("ai_context") or {}
        payload = build_prompt(
            task=task,
            ancestors=ancestors,
            thread=thread,
            mention=mention,
            persona=persona,
            ai_context=ai_context,
        )

        # 5. Acquire lock + stamp persona/version (so the dispatch is auditable
        #    even if we crash mid-way through).
        try:
            self._api.update_comment_props(mention.id, {
                "ai-comment-status": "dispatched",
                "ai-persona": persona.name,
                "ai-prompt-version": f"{persona.name}@{persona.version}",
            })
        except Exception:
            logger.exception("chat: failed to acquire lock for mention %s", mention.id)
            return

        # 6. Dispatch with retry
        retry_count = 0
        last_outcome: DispatchOutcome | None = None
        while retry_count < MAX_RETRIES:
            try:
                outcome = await self._dispatch_to_proxy(
                    payload=payload, task_id=task.id,
                )
            except Exception as e:
                logger.exception(
                    "chat: dispatch exception (attempt %d) for mention %s",
                    retry_count + 1,
                    mention.id,
                )
                outcome = DispatchOutcome(
                    success=False,
                    error=f"{type(e).__name__}: {str(e)[:300]}",
                    error_code="dispatch_exception",
                )
            last_outcome = outcome

            if outcome.success:
                self._finalize_success(mention, task, persona, outcome, retry_count)
                self._log_dispatch(mention, task, persona, outcome, "replied", retry_count)
                return

            retry_count += 1
            try:
                self._api.update_comment_props(
                    mention.id, {"ai-retry-count": retry_count}
                )
            except Exception:
                logger.exception(
                    "chat: failed to record retry count for mention %s", mention.id
                )

        # 7. Exhausted retries
        err = last_outcome.error if last_outcome else "exhausted_retries"
        code = (
            last_outcome.error_code if last_outcome and last_outcome.error_code
            else "exhausted_retries"
        )
        try:
            self._api.update_comment_props(mention.id, {
                "ai-comment-status": "failed",
                "ai-error": code,
                "ai-retry-count": retry_count,
            })
        except Exception:
            logger.exception("chat: failed to mark mention %s as failed", mention.id)
        logger.error(
            "chat: mention %s exhausted retries (%d). last_error=%s",
            mention.id,
            retry_count,
            err[:300],
        )
        self._log_dispatch(mention, task, persona, last_outcome, "failed", retry_count)

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
    def _task_has_dispatch_in_flight(
        all_comments: list[CommentEntity], current_mention_id: str
    ) -> bool:
        """True if any sibling mention on the same task is `dispatched`.

        Treats the current mention's own status as "not yet acquired" since we
        haven't flipped it yet at this point in the flow.
        """
        for c in all_comments:
            if c.id == current_mention_id:
                continue
            if c.props.get("ai-comment-status") == "dispatched":
                return True
        return False

    @staticmethod
    def _route_persona(mention_text: str) -> CompiledPersona:
        m = MENTION_RE.search(mention_text)
        suffix = m.group(1).lower() if m and m.group(1) else None
        return route_mention(suffix)

    async def _dispatch_to_proxy(
        self, *, payload: PromptPayload, task_id: str
    ) -> DispatchOutcome:
        """Submit job to proxy, poll until done. Parse inner JSON on success."""
        body = {
            "prompt": payload.user,
            "system_prompt": payload.system,
            "model": payload.model,
            "preferred_runtime": "claude",
            "fallback_runtimes": [],
            "allowed_tools": list(payload.allowed_tools),
            "disallowed_tools": [],
            "task_id": task_id,
            "workplanner_api_url": self._config.api_url,
            "internal_api_key": self._config.internal_api_key,
        }
        headers = {"Content-Type": "application/json"}
        if self._proxy_key:
            headers["X-Proxy-Key"] = self._proxy_key

        loop = asyncio.get_event_loop()

        # Submit
        submit = await loop.run_in_executor(
            None,
            lambda: requests.post(
                f"{self._proxy_url}/run",
                json=body,
                headers=headers,
                timeout=30,
            ),
        )
        if submit.status_code != 200:
            return DispatchOutcome(
                success=False,
                error=f"proxy /run returned {submit.status_code}: {submit.text[:300]}",
                error_code="proxy_submit_failed",
            )
        job_id = submit.json().get("job_id")
        if not job_id:
            return DispatchOutcome(
                success=False,
                error="proxy /run returned no job_id",
                error_code="proxy_submit_failed",
            )

        # Poll
        deadline = time.time() + PROXY_POLL_MAX_S
        while time.time() < deadline:
            await asyncio.sleep(PROXY_POLL_INTERVAL_S)
            try:
                resp = await loop.run_in_executor(
                    None,
                    lambda: requests.get(
                        f"{self._proxy_url}/status/{job_id}",
                        headers=headers,
                        timeout=15,
                    ),
                )
            except Exception as e:
                logger.warning("chat: status poll exception: %s", e)
                continue
            if resp.status_code != 200:
                continue
            data = resp.json()
            status = data.get("status", "")
            if status == "done":
                return self._parse_success_response(data)
            if status == "error":
                return DispatchOutcome(
                    success=False,
                    runtime=data.get("runtime", ""),
                    error=str(data.get("error", "unknown proxy error"))[:500],
                    error_code="proxy_runtime_error",
                    metadata=data.get("metadata") or {},
                )

        return DispatchOutcome(
            success=False,
            error=f"proxy did not complete within {PROXY_POLL_MAX_S}s",
            error_code="proxy_timeout",
        )

    @staticmethod
    def _parse_success_response(data: dict[str, Any]) -> DispatchOutcome:
        """Parse the proxy's `done` response into a DispatchOutcome.

        `data.result` is a string the AI emitted; expected to be JSON
        `{reply_text, context_update}`. Blank result or unparseable JSON
        becomes a retryable failure.
        """
        runtime = data.get("runtime", "")
        metadata = data.get("metadata") or {}
        result_str = (data.get("result") or "").strip()
        if not result_str:
            return DispatchOutcome(
                success=False,
                runtime=runtime,
                metadata=metadata,
                error="proxy returned empty result string",
                error_code="empty_reply",
            )
        try:
            inner = json.loads(result_str)
        except json.JSONDecodeError as e:
            return DispatchOutcome(
                success=False,
                runtime=runtime,
                metadata=metadata,
                error=f"inner JSON parse failed: {e}",
                error_code="malformed_output",
            )
        if not isinstance(inner, dict):
            return DispatchOutcome(
                success=False,
                runtime=runtime,
                metadata=metadata,
                error="inner output is not a JSON object",
                error_code="malformed_output",
            )

        reply_text = inner.get("reply_text", "")
        if not isinstance(reply_text, str) or not reply_text.strip():
            return DispatchOutcome(
                success=False,
                runtime=runtime,
                metadata=metadata,
                error="reply_text missing or empty",
                error_code="empty_reply",
            )
        context_update = inner.get("context_update", {})
        if not isinstance(context_update, dict):
            context_update = {}

        return DispatchOutcome(
            success=True,
            runtime=runtime,
            reply_text=reply_text,
            context_update=context_update,
            metadata=metadata,
        )

    def _finalize_success(
        self,
        mention: CommentEntity,
        task: TaskEntity,
        persona: CompiledPersona,
        outcome: DispatchOutcome,
        retry_count: int,
    ) -> None:
        """Post reply comment, merge ai_context, flip mention status.

        Not truly atomic — each is a separate API call. If a later step fails
        we may have a half-written state (e.g., reply visible but status still
        "dispatched"). v1 accepts this; the next poll will see the reply was
        posted and flip the status if we add detection. For now, log loudly.
        """
        # 1. Post reply
        reply_text = outcome.reply_text
        try:
            self._api.create_comment_with_props(
                task_id=mention.task_id,
                text=reply_text,
                parent_comment_id=mention.id,
                comment_type="COMMENT",
                created_by=f"ai-{persona.name}",
                props={},
            )
        except Exception:
            logger.exception(
                "chat: failed to post reply for mention %s; mention state may be inconsistent",
                mention.id,
            )
            return

        # 2. Merge context_update
        if outcome.context_update:
            ai_context_patch = {
                "ai_context": {
                    **outcome.context_update,
                    "last_updated_by": f"ai-{persona.name}",
                    "last_updated_at": int(time.time() * 1000),
                }
            }
            try:
                self._api.update_task(task.id, props=ai_context_patch)
            except Exception:
                logger.exception(
                    "chat: failed to merge ai_context for task %s after reply was posted",
                    task.id,
                )

        # 3. Flip mention status + stamp telemetry
        telemetry = _telemetry_from_metadata(outcome.metadata)
        try:
            self._api.update_comment_props(mention.id, {
                "ai-comment-status": "replied",
                "ai-retry-count": retry_count,
                **telemetry,
            })
        except Exception:
            logger.exception(
                "chat: failed to flip status to 'replied' for mention %s",
                mention.id,
            )

    @staticmethod
    def _log_dispatch(
        mention: CommentEntity,
        task: TaskEntity,
        persona: CompiledPersona,
        outcome: DispatchOutcome | None,
        terminal: str,
        retry_count: int,
    ) -> None:
        """Structured JSON line per dispatch — easy to grep in Railway logs."""
        payload: dict[str, Any] = {
            "event": "chat_dispatch",
            "mention_id": mention.id,
            "task_id": task.id,
            "persona": persona.name,
            "persona_version": persona.version,
            "terminal": terminal,
            "retry_count": retry_count,
        }
        if outcome is not None:
            payload.update({
                "runtime": outcome.runtime,
                "duration_ms": outcome.metadata.get("duration_ms"),
                "cost_usd": outcome.metadata.get("total_cost_usd"),
                "stop_reason": outcome.metadata.get("stop_reason"),
                "error_code": outcome.error_code or None,
            })
        logger.info(json.dumps(payload))


# ─── Telemetry extraction ─────────────────────────────────────────────────


def _telemetry_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Pull the comments.props telemetry keys out of the proxy metadata envelope."""
    if not metadata:
        return {}
    out: dict[str, Any] = {}
    if "duration_ms" in metadata:
        out["ai-duration-ms"] = metadata["duration_ms"]
    if "total_cost_usd" in metadata:
        out["ai-cost-usd"] = metadata["total_cost_usd"]
    if "stop_reason" in metadata:
        out["ai-stop-reason"] = metadata["stop_reason"]
    usage = metadata.get("usage")
    if isinstance(usage, dict):
        out["ai-tokens"] = {
            "input": usage.get("input_tokens"),
            "output": usage.get("output_tokens"),
            "cache_read": usage.get("cache_read_input_tokens"),
            "cache_creation": usage.get("cache_creation_input_tokens"),
        }
    # Model used: prefer the explicit key from modelUsage if present.
    model_usage = metadata.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        # First key is the model id used.
        out["ai-model"] = next(iter(model_usage.keys()))
    return out
