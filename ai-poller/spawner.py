"""Agent spawning — calls the Claude proxy server on the user's Mac.

The proxy runs claude -p with the user's subscription auth.
MCP tools run on the Mac via the proxy's MCP config.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from algorithm import Algorithm, SpawnPlan, TaskContext
from api_client import ApiClient
from config import Config
from knowledge import KnowledgeBase
from models import TaskEntity

logger = logging.getLogger(__name__)


@dataclass
class AgentRun:
    """Tracks a single agent run."""
    task_id: str
    algorithm_name: str
    started_at: float = field(default_factory=time.time)
    task_handle: asyncio.Task | None = None


class AgentSpawner:
    """Manages spawning and tracking of Claude agent runs via the proxy."""

    def __init__(self, api: ApiClient, config: Config) -> None:
        self._api = api
        self._config = config
        self._active_runs: dict[str, AgentRun] = {}
        self._proxy_url = os.environ.get("CLAUDE_PROXY_URL", "http://localhost:8400")
        self._proxy_key = os.environ.get("CLAUDE_PROXY_KEY", "")

    @property
    def active_count(self) -> int:
        return len(self._active_runs)

    def is_running(self, task_id: str) -> bool:
        return task_id in self._active_runs

    def can_spawn(self) -> bool:
        return self.active_count < self._config.agent_limits.max_global_agents

    async def spawn(
        self,
        task: TaskEntity,
        plan: SpawnPlan,
        algorithm: Algorithm,
        knowledge: KnowledgeBase | None = None,
    ) -> None:
        if self.is_running(task.id):
            logger.warning("Agent already running for task %s, skipping", task.id)
            return

        if not self.can_spawn():
            logger.warning("Agent limit reached (%d), cannot spawn for task %s",
                           self._config.agent_limits.max_global_agents, task.id)
            return

        ai_status = task.props.get("aiStatus", "needs_planning")
        logger.info("Spawning %s agent for task '%s' (%s) [aiStatus=%s, model=%s]",
                     algorithm.name, task.title, task.id, ai_status, plan.model)

        # Enrich prompt with knowledge context
        system_prompt = plan.prompt
        if knowledge:
            try:
                context = knowledge.query_knowledge(
                    f"context for: {task.title} {task.description}",
                    limit=3,
                )
                if context:
                    knowledge_section = "\n\nRelevant knowledge from previous work:\n"
                    for doc in context:
                        knowledge_section += f"- {doc['document'][:200]}\n"
                    system_prompt += knowledge_section
            except Exception:
                logger.warning("Failed to query knowledge base for task %s", task.id)

        run = AgentRun(task_id=task.id, algorithm_name=algorithm.name)
        self._active_runs[task.id] = run

        run.task_handle = asyncio.create_task(
            self._run_agent(task, system_prompt, plan, algorithm, knowledge)
        )

    async def _run_agent(
        self,
        task: TaskEntity,
        system_prompt: str,
        plan: SpawnPlan,
        algorithm: Algorithm,
        knowledge: KnowledgeBase | None = None,
    ) -> None:
        task_id = task.id
        try:
            # Extract algo tools from the plan
            _, allowed_tools = plan.tools
            extra_mcp_servers = plan.tools[0]

            # Determine which algo tools to enable
            algo_tools: list[str] = []
            if "algo" in extra_mcp_servers:
                # The algo MCP server object has tools registered —
                # we need to figure out which tools based on the phase.
                # The allowed_tools list has patterns like "mcp__algo__*"
                # We pass all algo tool names and let the server filter.
                algo_tools = plan.metadata.get("algo_tools", [])

            prompt = (
                f"You have been assigned task {task_id}. "
                f"Begin by reviewing your task and any existing comments, "
                f"then take appropriate action based on your instructions."
            )

            # Build request to proxy
            request_body = {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "model": plan.model,
                "max_turns": self._config.agent_limits.max_turns_per_run,
                "allowed_tools": allowed_tools,
                "algo_tools": algo_tools,
                "task_id": task_id,
                "ai_status": task.props.get("aiStatus", ""),
                "workplanner_api_url": self._config.api_url,
                "internal_api_key": self._config.internal_api_key,
            }

            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._proxy_key:
                headers["X-Proxy-Key"] = self._proxy_key

            logger.info("Calling proxy for task %s: %s/run", task_id, self._proxy_url)

            # Make the HTTP call in a thread to not block the event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self._proxy_url}/run",
                    json=request_body,
                    headers=headers,
                    timeout=660,  # slightly longer than proxy's 600s timeout
                ),
            )

            if response.status_code != 200:
                logger.error("Proxy error for task %s: %d %s",
                             task_id, response.status_code, response.text[:500])
                return

            result = response.json()
            result_text = result.get("result", "")
            success = result.get("success", False)

            if success and result_text:
                logger.info("Agent result for task %s: %s", task_id, result_text[:500])
            elif not success:
                logger.warning("Agent failed for task %s: %s",
                               task_id, result.get("error", "unknown")[:500])
            else:
                logger.warning("Agent produced no result for task %s", task_id)

            # Run on_complete
            try:
                fresh_comments = self._api.list_comments(task_id)
                all_tasks = self._api.get_all_tasks()
                fresh_children = [t for t in all_tasks if t.parent_id == task_id]
                fresh_task = self._api.get_task(task_id)
                children_comments = {
                    child.id: self._api.list_comments(child.id)
                    for child in fresh_children
                }
                ctx = TaskContext(
                    task=fresh_task,
                    comments=fresh_comments,
                    children=fresh_children,
                    parent=next((t for t in all_tasks if t.id == task.parent_id), None) if task.parent_id else None,
                    children_comments=children_comments,
                )
                props_update = plan.on_complete(ctx, result_text)
                if props_update:
                    old_status = task.props.get("aiStatus", "unset")
                    new_status = props_update.self_props.get("aiStatus", old_status)
                    logger.info("Task %s: state %s → %s (props: %s)",
                                task_id, old_status, new_status, props_update.self_props)
                    self._api.update_task(task_id, props=props_update.self_props)
                    if props_update.child_props:
                        for child in fresh_children:
                            if not child.props.get("algorithm"):
                                logger.info("Task %s: setting child %s props: %s",
                                            task_id, child.id, props_update.child_props)
                                self._api.update_task(child.id, props=props_update.child_props)
            except Exception:
                logger.exception("Failed to run on_complete for task %s", task_id)

            # Document in knowledge base
            if knowledge and result_text:
                try:
                    knowledge.document_work(
                        task_id=task_id,
                        agent_id=task_id,
                        work_type="agent_run",
                        content=result_text[:2000],
                    )
                except Exception:
                    logger.warning("Failed to document work for task %s", task_id)

            logger.info("Agent run completed for task %s", task_id)

        except asyncio.CancelledError:
            logger.warning("Agent run cancelled for task %s", task_id)
        except Exception:
            logger.exception("Agent run failed for task %s", task_id)
        finally:
            self._active_runs.pop(task_id, None)

    async def wait_for_all(self, timeout: float | None = None) -> None:
        handles = [
            run.task_handle for run in self._active_runs.values()
            if run.task_handle is not None
        ]
        if handles:
            await asyncio.wait(handles, timeout=timeout)

    async def cancel_all(self) -> None:
        for run in list(self._active_runs.values()):
            if run.task_handle and not run.task_handle.done():
                run.task_handle.cancel()
        await self.wait_for_all(timeout=5.0)
        self._active_runs.clear()

    def cleanup_stale(self, max_age_seconds: float = 3600) -> int:
        now = time.time()
        stale = [
            task_id for task_id, run in self._active_runs.items()
            if now - run.started_at > max_age_seconds
        ]
        for task_id in stale:
            run = self._active_runs.pop(task_id)
            if run.task_handle and not run.task_handle.done():
                run.task_handle.cancel()
            logger.warning("Cleaned up stale agent run for task %s (age: %.0fs)",
                           task_id, now - run.started_at)
        return len(stale)
