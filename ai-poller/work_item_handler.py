"""Work-item dispatcher — turns pending WorkItems into AI invocations.

Second poller in the two-poller pipeline (see docs/WORK_ITEMS_DESIGN.md).
`chat_handler` produces WorkItems from comment mentions; this handler
consumes them.

Flow per poll cycle:
  1. Fetch WorkItems eligible for pickup (pending OR
     failed-with-retries-remaining), oldest first.
  2. For each, check the per-task in-flight cap (max 2 dispatched per task).
  3. Transition pending → dispatched (server-side state machine guards).
  4. POST /run to claude-proxy with prompt_context (already rendered by
     chat_handler).
  5. Poll proxy /status until done or timeout.
  6. On success:
     a. Parse inner JSON {reply_text, artifacts?, context_update?}.
     b. POST /work-items/:id/submit-output with the structured output.
     c. Post a threaded reply comment (parent_comment_id =
        triggering_comment_id) carrying reply_text + work_item_id in props.
     d. Optionally merge context_update into task.props.ai_context.
  7. On failure: POST /work-items/:id/record-attempt; retry happens
     automatically on the next cycle (until retry_count == max_retries).

This handler never decides whether to dispatch — that's the work item's
status. It just executes what's in the queue.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests
import os

from api_client import ApiClient
from config import Config
from models import WorkItemEntity

logger = logging.getLogger(__name__)


PROXY_POLL_INTERVAL_S = 5
# How long the poller waits for the proxy to return a result. Must be >=
# the proxy's own runtime wall-clock cap (PROXY_RUN_TIMEOUT_SECONDS) or
# the poller times out on dispatches the proxy is still legitimately
# running, burning retries on healthy runs. Default 30 min matches the
# proxy's default + a small buffer.
PROXY_POLL_MAX_S = int(os.environ.get("WORK_ITEM_PROXY_POLL_MAX_S", "1800"))
PER_TASK_CONCURRENCY = 2  # at most this many dispatched WorkItems per task


# ─── Dispatch outcome ─────────────────────────────────────────────────────


@dataclass
class DispatchOutcome:
    success: bool
    runtime: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""


# ─── Work-item handler ────────────────────────────────────────────────────


class WorkItemHandler:
    def __init__(self, api: ApiClient, config: Config) -> None:
        self._api = api
        self._config = config
        self._proxy_url = os.environ.get("CLAUDE_PROXY_URL", "http://localhost:8400")
        self._proxy_key = os.environ.get("CLAUDE_PROXY_KEY", "")

    # ─── Public API ───────────────────────────────────────────────────────

    async def run_cycle(self) -> int:
        """One dispatch cycle. Returns number of WorkItems acted on."""
        try:
            candidates = self._api.list_work_items_for_pickup()
        except Exception:
            logger.exception("work_item_handler: failed to list pickup queue")
            return 0

        if not candidates:
            return 0

        # Per-task concurrency cap: don't dispatch more than N at a time per task.
        dispatched_per_task: dict[str, int] = {}
        for w in candidates:
            try:
                dispatched_per_task[w.task_id] = self._api.list_work_items(
                    task_id=w.task_id, status="dispatched",
                ).__len__()
            except Exception:
                logger.exception(
                    "work_item_handler: failed to count dispatched for task %s", w.task_id
                )
                dispatched_per_task[w.task_id] = PER_TASK_CONCURRENCY  # block

        handled = 0
        for w in candidates:
            if dispatched_per_task[w.task_id] >= PER_TASK_CONCURRENCY:
                logger.info(
                    "work_item_handler: task %s at concurrency cap; skipping WorkItem %s",
                    w.task_id, w.id,
                )
                continue
            try:
                if await self._dispatch_work_item(w):
                    handled += 1
                    dispatched_per_task[w.task_id] += 1
            except Exception:
                logger.exception(
                    "work_item_handler: unhandled error on WorkItem %s", w.id
                )
        return handled

    # ─── Per-WorkItem pipeline ────────────────────────────────────────────

    async def _dispatch_work_item(self, w: WorkItemEntity) -> bool:
        """Dispatch one WorkItem end-to-end. Returns True on terminal
        transition (completed or failed); False if we skipped early."""

        # Transition to dispatched. The state machine rejects re-dispatch
        # of already-dispatched items, so this is also the lock.
        try:
            w = self._api.update_work_item(w.id, status="dispatched")
        except Exception:
            logger.exception(
                "work_item_handler: failed to acquire lock on WorkItem %s", w.id
            )
            return False

        outcome = await self._invoke_proxy(w)

        if outcome.success:
            return self._finalize_success(w, outcome)
        return self._finalize_failure(w, outcome)

    async def _invoke_proxy(self, w: WorkItemEntity) -> DispatchOutcome:
        """Submit job to proxy and poll until done. Parse inner JSON."""
        ctx = w.prompt_context or {}
        body = {
            "prompt": ctx.get("user", ""),
            "system_prompt": ctx.get("system", ""),
            "model": ctx.get("model", ""),
            "preferred_runtime": "claude",
            "fallback_runtimes": [],
            "max_turns": int(ctx.get("max_turns", 20)),
            "allowed_tools": list(ctx.get("allowed_tools", [])),
            "disallowed_tools": [],
            "task_id": w.task_id,
            "work_item_id": w.id,
            "workplanner_api_url": self._config.api_url,
            "internal_api_key": self._config.internal_api_key,
        }
        headers = {"Content-Type": "application/json"}
        if self._proxy_key:
            headers["X-Proxy-Key"] = self._proxy_key

        loop = asyncio.get_event_loop()

        # Submit
        try:
            submit = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self._proxy_url}/run", json=body, headers=headers, timeout=30
                ),
            )
        except Exception as e:
            return DispatchOutcome(
                success=False,
                error=f"proxy /run exception: {type(e).__name__}: {str(e)[:300]}",
            )

        if submit.status_code != 200:
            return DispatchOutcome(
                success=False,
                error=f"proxy /run returned {submit.status_code}: {submit.text[:300]}",
            )
        job_id = submit.json().get("job_id")
        if not job_id:
            return DispatchOutcome(
                success=False, error="proxy /run returned no job_id"
            )

        # Poll
        deadline = time.time() + PROXY_POLL_MAX_S
        while time.time() < deadline:
            await asyncio.sleep(PROXY_POLL_INTERVAL_S)
            try:
                resp = await loop.run_in_executor(
                    None,
                    lambda: requests.get(
                        f"{self._proxy_url}/status/{job_id}", headers=headers, timeout=15
                    ),
                )
            except Exception as e:
                logger.warning("work_item_handler: status poll exception: %s", e)
                continue
            if resp.status_code != 200:
                continue
            data = resp.json()
            status = data.get("status", "")
            if status == "done":
                return _parse_proxy_done(data)
            if status == "error":
                return DispatchOutcome(
                    success=False,
                    runtime=data.get("runtime", ""),
                    metadata=data.get("metadata") or {},
                    error=str(data.get("error", "unknown proxy error"))[:500],
                )

        return DispatchOutcome(
            success=False,
            error=f"proxy did not complete within {PROXY_POLL_MAX_S}s",
        )

    # ─── Terminal transitions ─────────────────────────────────────────────

    def _finalize_success(self, w: WorkItemEntity, outcome: DispatchOutcome) -> bool:
        """Submit output to backend, post threaded reply comment, merge
        context_update into task.props.ai_context."""

        output = {
            **outcome.output,
            # Stamp telemetry from the proxy run alongside the AI's output.
            "metadata": {
                **outcome.output.get("metadata", {}),
                "proxy_metadata": outcome.metadata,
                "runtime": outcome.runtime,
            },
        }

        # 1. Persist output + flip status. If this fails we're in a bad spot;
        #    log loudly. WorkItem stays in dispatched until manual cleanup.
        try:
            self._api.submit_work_item_output(w.id, output)
        except Exception:
            logger.exception(
                "work_item_handler: failed to submit output for WorkItem %s", w.id
            )
            return False

        # 2. Post reply comment (threaded under the triggering mention).
        reply_text = (outcome.output.get("reply_text") or "").strip()
        if reply_text:
            persona_name = (w.prompt_context or {}).get("persona_name", w.target_persona)
            try:
                self._api.create_comment_with_props(
                    task_id=w.task_id,
                    text=reply_text,
                    parent_comment_id=w.triggering_comment_id,
                    comment_type="COMMENT",
                    created_by=f"ai-{persona_name}",
                    props={
                        "work_item_id": w.id,
                        **_telemetry_props(outcome.metadata),
                    },
                )
            except Exception:
                logger.exception(
                    "work_item_handler: failed to post reply comment for WorkItem %s",
                    w.id,
                )

        # 3. Merge context_update into task.props.ai_context (best-effort).
        context_update = outcome.output.get("context_update")
        if isinstance(context_update, dict) and context_update:
            try:
                persona_name = (w.prompt_context or {}).get("persona_name", w.target_persona)
                self._api.update_task(w.task_id, props={
                    "ai_context": {
                        **context_update,
                        "last_updated_by": f"ai-{persona_name}",
                        "last_updated_at": int(time.time() * 1000),
                    }
                })
            except Exception:
                logger.exception(
                    "work_item_handler: failed to merge ai_context for task %s",
                    w.task_id,
                )

        # 4. Update the triggering comment's status (completes the loop).
        if w.triggering_comment_id:
            try:
                self._api.update_comment_props(
                    w.triggering_comment_id, {"ai-comment-status": "replied"}
                )
            except Exception:
                logger.exception(
                    "work_item_handler: failed to flip triggering-comment status (work_item=%s)",
                    w.id,
                )

        self._log_terminal(w, outcome, "completed")
        return True

    def _finalize_failure(self, w: WorkItemEntity, outcome: DispatchOutcome) -> bool:
        """Record the failed attempt. Auto-retry happens on the next cycle
        until retry_count == max_retries."""
        try:
            updated = self._api.record_work_item_attempt(
                w.id,
                error=outcome.error or "unknown failure",
                duration_ms=outcome.metadata.get("duration_ms"),
                cost_usd=outcome.metadata.get("total_cost_usd"),
                runtime=outcome.runtime,
                model=outcome.metadata.get("model", ""),
                stop_reason=outcome.metadata.get("stop_reason", ""),
            )
        except Exception:
            logger.exception(
                "work_item_handler: failed to record attempt for WorkItem %s", w.id
            )
            return False

        self._log_terminal(w, outcome, "failed")
        if updated.retry_count >= updated.max_retries:
            logger.error(
                "work_item_handler: WorkItem %s exhausted retries (%d/%d). Manual unstick required.",
                w.id, updated.retry_count, updated.max_retries,
            )
        return True

    # ─── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _log_terminal(
        w: WorkItemEntity, outcome: DispatchOutcome, terminal: str
    ) -> None:
        payload: dict[str, Any] = {
            "event": "work_item_dispatch",
            "work_item_id": w.id,
            "task_id": w.task_id,
            "persona": w.target_persona,
            "terminal": terminal,
            "runtime": outcome.runtime,
            "duration_ms": outcome.metadata.get("duration_ms"),
            "cost_usd": outcome.metadata.get("total_cost_usd"),
            "stop_reason": outcome.metadata.get("stop_reason"),
        }
        if not outcome.success:
            payload["error"] = outcome.error[:300]
        logger.info(json.dumps(payload))


# ─── Module helpers ───────────────────────────────────────────────────────


def _parse_proxy_done(data: dict[str, Any]) -> DispatchOutcome:
    """Parse the proxy's `done` envelope into a DispatchOutcome.

    `data["result"]` is a JSON string the AI emitted; expected shape is
    `{reply_text, artifacts?, context_update?}`. Empty or unparseable
    becomes a failure (the work_item_handler will retry).
    """
    runtime = data.get("runtime", "")
    metadata = data.get("metadata") or {}
    result_str = (data.get("result") or "").strip()
    if not result_str:
        return DispatchOutcome(
            success=False, runtime=runtime, metadata=metadata,
            error="proxy returned empty result string",
        )
    try:
        inner = json.loads(result_str)
    except json.JSONDecodeError as e:
        return DispatchOutcome(
            success=False, runtime=runtime, metadata=metadata,
            error=f"inner JSON parse failed: {e}",
        )
    if not isinstance(inner, dict):
        return DispatchOutcome(
            success=False, runtime=runtime, metadata=metadata,
            error="inner output is not a JSON object",
        )
    reply_text = inner.get("reply_text", "")
    if not isinstance(reply_text, str) or not reply_text.strip():
        return DispatchOutcome(
            success=False, runtime=runtime, metadata=metadata,
            error="reply_text missing or empty",
        )
    return DispatchOutcome(
        success=True, runtime=runtime, output=inner, metadata=metadata,
    )


def _telemetry_props(metadata: dict[str, Any]) -> dict[str, Any]:
    """Extract telemetry keys from the proxy metadata envelope and shape them
    as props for the reply comment (mirrors the old chat_handler behavior so
    UI/CLI consumers keep working)."""
    out: dict[str, Any] = {}
    if not metadata:
        return out
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
    model_usage = metadata.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        out["ai-model"] = next(iter(model_usage.keys()))
    return out
