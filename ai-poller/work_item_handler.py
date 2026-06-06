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

# The fixer normalizer runs on EVERY dispatch (it is the sole producer of the
# canonical JSON — the main persona never needs to emit JSON). Persona
# frontmatter may override the model via `fixer_model`; otherwise this default
# applies. Env-overridable for ops tuning.
DEFAULT_FIXER_MODEL = os.environ.get("WORK_ITEM_FIXER_MODEL", "claude-sonnet-4-6")


# System prompt for the normalizer/fixer pass. The fixer's only job is to
# extract the canonical JSON shape from an arbitrary AI agent's output. It
# runs on every dispatch, so personas can reply naturally and the fixer
# enforces the schema.
FIXER_SYSTEM_PROMPT = """You are a normalizer. Your input is the raw \
stdout of another AI agent (an "engineer", "manager", "planner", or \
similar persona running with tool access). That output may contain prose, \
markdown, code fences, planning aloud, partial JSON, multiple JSON \
blocks, or any combination — agents drift from format under long prompts.

Your only job is to extract that agent's communication into this exact \
JSON object:

{
  "reply_text":     "<string, REQUIRED — the agent's prose communication \
to the human reader, cleaned of meta-commentary like 'Let me write the \
reply' or 'Here is my response'>",
  "artifacts":      <object, OPTIONAL — structured facts the agent \
reported (branch, commits, tests, scope checks, etc.); preserve whatever \
field names the agent used; do not invent or paraphrase>,
  "context_update": <object, OPTIONAL — context patch the agent emitted \
for task.props.ai_context>
}

Rules:
- Output ONLY the JSON object. No prose around it, no markdown code \
fences, no explanation.
- If the agent already emitted JSON inline, extract its fields verbatim. \
Do not summarize, paraphrase, or invent values.
- reply_text should be the agent's substantive human-readable reply, \
posted as-is into a comment thread. Markdown is fine. Strip meta- \
commentary about formatting; keep substantive content (findings, \
verdicts, hand-offs to other personas, questions).
- If the agent's output contains nothing recoverable, return:
  {"_fixer_failed": true, "reason": "<one-line explanation>"}
- You are a translator, not a generator. Never add fields the agent did \
not produce. If artifacts is missing, omit the key — do not invent one.
"""

# Cap on how much raw text we embed in error messages when the fixer (or
# strict parser) fails. Survives Postgres JSONB size limits + keeps wp
# work-items show readable.
_RAW_OUTPUT_CAP = 8000


# ─── Dispatch outcome ─────────────────────────────────────────────────────


@dataclass
class DispatchOutcome:
    success: bool
    runtime: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class _ProxyCall:
    """Result of a single submit-and-poll round-trip to the proxy. The
    `_invoke_proxy` orchestrator uses two of these (main + optional fixer)
    and merges them into a DispatchOutcome."""
    ok: bool
    raw_result: str = ""        # only meaningful when ok=True
    runtime: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""             # only meaningful when ok=False


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
        """Run the main persona dispatch, optionally followed by a fixer
        normalizer pass that translates raw output into the canonical JSON
        schema.

        Flow:
          1. Submit the persona's prompt to the proxy. Wait for done/error.
          2. If `prompt_context.fixer_model` is set on the WorkItem, take the
             raw result string and submit a second job to the fixer with a
             system prompt that extracts {reply_text, artifacts,
             context_update}. The persona is free to emit any shape; the
             fixer is the schema enforcer.
          3. Parse the final JSON (from either the fixer's output or, when
             fixer is disabled, the persona's raw output).

        Failures at any stage become a DispatchOutcome with success=False;
        the caller records an attempt and the WorkItem auto-retries.
        """
        ctx = w.prompt_context or {}
        main_body = {
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

        # ── Main dispatch ──────────────────────────────────────────────
        main_outcome = await self._submit_and_poll(main_body)
        if not main_outcome.ok:
            return DispatchOutcome(
                success=False,
                runtime=main_outcome.runtime,
                metadata=main_outcome.metadata,
                error=main_outcome.error,
            )

        raw_result = main_outcome.raw_result
        main_metadata = main_outcome.metadata
        main_runtime = main_outcome.runtime

        # ── Fixer pass (always on) ─────────────────────────────────────
        # The fixer ALWAYS runs and is the sole producer of the canonical
        # JSON — the main persona never needs to emit JSON, it just talks.
        # This removes the strict-parse-the-persona-output path entirely, so
        # a dispatch can't fail just because the persona replied in prose /
        # markdown / fenced JSON. Persona frontmatter may override the fixer
        # model; otherwise DEFAULT_FIXER_MODEL is used.
        fixer_model = (ctx.get("fixer_model") or "").strip() or DEFAULT_FIXER_MODEL
        fixer_body = {
            "prompt": raw_result,
            "system_prompt": FIXER_SYSTEM_PROMPT,
            "model": fixer_model,
            "preferred_runtime": "claude",
            "fallback_runtimes": [],
            "max_turns": int(ctx.get("fixer_max_turns", 50)),
            # Fixer is pure text-to-text; no MCP tools so it can't get
            # distracted reading the task or making side effects.
            "allowed_tools": [],
            "disallowed_tools": [],
            "task_id": w.task_id,
            "work_item_id": w.id,
            "workplanner_api_url": self._config.api_url,
            "internal_api_key": self._config.internal_api_key,
        }
        fixer_outcome = await self._submit_and_poll(fixer_body)
        if not fixer_outcome.ok:
            return DispatchOutcome(
                success=False,
                runtime=main_runtime,
                metadata={
                    **main_metadata,
                    "fixer_metadata": fixer_outcome.metadata,
                    "fixer_error": fixer_outcome.error,
                },
                error=f"fixer pass failed: {fixer_outcome.error}",
            )
        # The fixer's response should be the canonical JSON. Parse it.
        parsed = _parse_result_str(
            fixer_outcome.raw_result,
            runtime=main_runtime,
            metadata={
                **main_metadata,
                "fixer_metadata": fixer_outcome.metadata,
                "fixer_model": fixer_model,
                "normalized": True,
            },
        )
        # Detect explicit fixer-failure marker.
        if parsed.success and parsed.output.get("_fixer_failed"):
            return DispatchOutcome(
                success=False,
                runtime=main_runtime,
                metadata=parsed.metadata,
                error=(
                    f"fixer declined to normalize: "
                    f"{parsed.output.get('reason', 'no reason given')}\n"
                    f"---RAW PERSONA OUTPUT (first {_RAW_OUTPUT_CAP} chars)---\n"
                    f"{raw_result[:_RAW_OUTPUT_CAP]}"
                ),
            )
        return parsed

    async def _submit_and_poll(self, body: dict[str, Any]) -> "_ProxyCall":
        """Submit a job to the proxy and poll until it terminates. Returns
        the raw result string on success; never parses inner JSON (caller's
        job). Used for both the main persona dispatch and the fixer pass."""
        headers = {"Content-Type": "application/json"}
        if self._proxy_key:
            headers["X-Proxy-Key"] = self._proxy_key

        loop = asyncio.get_event_loop()

        try:
            submit = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self._proxy_url}/run", json=body, headers=headers, timeout=30
                ),
            )
        except Exception as e:
            return _ProxyCall(
                ok=False,
                error=f"proxy /run exception: {type(e).__name__}: {str(e)[:300]}",
            )

        if submit.status_code != 200:
            return _ProxyCall(
                ok=False,
                error=f"proxy /run returned {submit.status_code}: {submit.text[:300]}",
            )
        job_id = submit.json().get("job_id")
        if not job_id:
            return _ProxyCall(ok=False, error="proxy /run returned no job_id")

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
                return _ProxyCall(
                    ok=True,
                    raw_result=(data.get("result") or "").strip(),
                    runtime=data.get("runtime", ""),
                    metadata=data.get("metadata") or {},
                )
            if status == "error":
                return _ProxyCall(
                    ok=False,
                    runtime=data.get("runtime", ""),
                    metadata=data.get("metadata") or {},
                    error=str(data.get("error", "unknown proxy error"))[:500],
                )

        return _ProxyCall(
            ok=False,
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


def _strip_code_fences(s: str) -> str:
    """Strip a leading ```json / ``` fence and trailing ``` if the whole
    string is a fenced block. The fixer is told not to fence, but models do
    it anyway; since the fixer's output is now the SOLE parse point (its
    failure would burn all retries), we defensively unwrap it."""
    t = s.strip()
    if t.startswith("```"):
        # drop the opening fence line (``` or ```json)
        nl = t.find("\n")
        if nl != -1:
            t = t[nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _parse_result_str(
    result_str: str,
    runtime: str = "",
    metadata: dict[str, Any] | None = None,
) -> DispatchOutcome:
    """Parse a JSON result string (the fixer's output) into a DispatchOutcome.

    The fixer normalizer runs on every dispatch and is the sole producer of
    the canonical JSON, so this is where its output is validated. Tolerates
    a fenced ```json block (defensive — a fixer fence would otherwise fail
    all retries). On parse failure we embed the raw text in the error so it's
    visible via `wp work-items show` — the proxy's job TTL (5 min) GCs the
    only other copy.
    """
    metadata = metadata or {}
    if not result_str:
        return DispatchOutcome(
            success=False, runtime=runtime, metadata=metadata,
            error="proxy returned empty result string",
        )
    result_str = _strip_code_fences(result_str)
    try:
        inner = json.loads(result_str)
    except json.JSONDecodeError as e:
        return DispatchOutcome(
            success=False, runtime=runtime, metadata=metadata,
            error=(
                f"inner JSON parse failed: {e}\n"
                f"---RAW OUTPUT (first {_RAW_OUTPUT_CAP} chars)---\n"
                f"{result_str[:_RAW_OUTPUT_CAP]}"
            ),
        )
    if not isinstance(inner, dict):
        return DispatchOutcome(
            success=False, runtime=runtime, metadata=metadata,
            error=(
                f"inner output is not a JSON object (got {type(inner).__name__})\n"
                f"---RAW OUTPUT (first {_RAW_OUTPUT_CAP} chars)---\n"
                f"{result_str[:_RAW_OUTPUT_CAP]}"
            ),
        )
    # The fixer's signal-failure response. Caller (_invoke_proxy) handles
    # this by surfacing a DispatchOutcome failure that retries the whole
    # pass.
    if inner.get("_fixer_failed"):
        return DispatchOutcome(
            success=True, runtime=runtime, output=inner, metadata=metadata,
        )
    reply_text = inner.get("reply_text", "")
    if not isinstance(reply_text, str) or not reply_text.strip():
        return DispatchOutcome(
            success=False, runtime=runtime, metadata=metadata,
            error=(
                "reply_text missing or empty\n"
                f"---PARSED INNER JSON (keys: {list(inner.keys())})---\n"
                f"{json.dumps(inner, indent=2)[:_RAW_OUTPUT_CAP]}"
            ),
        )
    return DispatchOutcome(
        success=True, runtime=runtime, output=inner, metadata=metadata,
    )


# Back-compat alias for tests that still import the old name. New code
# should call _parse_result_str directly.
def _parse_proxy_done(data: dict[str, Any]) -> DispatchOutcome:
    return _parse_result_str(
        (data.get("result") or "").strip(),
        runtime=data.get("runtime", ""),
        metadata=data.get("metadata") or {},
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
