"""Agent spawning — launches Claude Agent SDK sub-agents for tasks.

Handles agent lifecycle: spawn, monitor, timeout, cleanup.
Respects concurrency limits from config.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)

from algo_tools import set_algo_context
from algorithm import Algorithm, SpawnPlan, TaskContext
from api_client import ApiClient
from config import Config
from knowledge import KnowledgeBase
from models import TaskEntity
from task_tools import set_api_client, create_workplanner_mcp_server

logger = logging.getLogger(__name__)


@dataclass
class AgentRun:
    """Tracks a single agent run."""
    task_id: str
    algorithm_name: str
    started_at: float = field(default_factory=time.time)
    task_handle: asyncio.Task | None = None


class AgentSpawner:
    """Manages spawning and tracking of Claude agent sub-agents."""

    def __init__(self, api: ApiClient, config: Config) -> None:
        self._api = api
        self._config = config
        self._active_runs: dict[str, AgentRun] = {}  # task_id -> AgentRun

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
        """Spawn a Claude agent for the given task using the provided plan."""
        if self.is_running(task.id):
            logger.warning("Agent already running for task %s, skipping", task.id)
            return

        if not self.can_spawn():
            logger.warning("Agent limit reached (%d), cannot spawn for task %s",
                           self._config.agent_limits.max_global_agents, task.id)
            return

        ai_status = task.props.get("aiStatus", "needs_planning")
        logger.info("Spawning %s agent for task '%s' (%s) [aiStatus=%s]",
                     algorithm.name, task.title, task.id, ai_status)

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

        # Register run
        run = AgentRun(task_id=task.id, algorithm_name=algorithm.name)
        self._active_runs[task.id] = run

        # Launch async
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
        """Execute one agent run for a task."""
        task_id = task.id
        try:
            set_api_client(self._api)
            set_algo_context(self._api, task_id, task.props.get("aiStatus", ""))
            workplanner_mcp = create_workplanner_mcp_server()

            extra_mcp_servers, allowed_tools = plan.tools
            mcp_servers: dict[str, Any] = {"workplanner": workplanner_mcp}
            mcp_servers.update(extra_mcp_servers)

            prompt = (
                f"You have been assigned task {task_id}. "
                f"Begin by reviewing your task and any existing comments, "
                f"then take appropriate action based on your instructions."
            )

            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                mcp_servers=mcp_servers,
                allowed_tools=allowed_tools,
                max_turns=self._config.agent_limits.max_turns_per_run,
                model=plan.model,
                env={"ANTHROPIC_API_KEY": self._config.anthropic_api_key},
            )

            result_text = ""
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                async for message in client.receive_response():
                    logger.info("Agent message for task %s: type=%s subtype=%s",
                                task_id, type(message).__name__, getattr(message, 'subtype', ''))
                    if isinstance(message, ResultMessage):
                        if message.subtype == "success":
                            result_text = message.result
                        else:
                            logger.warning("Agent non-success result for task %s: subtype=%s",
                                           task_id, message.subtype)

            if result_text:
                logger.info("Agent result for task %s: %s", task_id, result_text[:500])
            else:
                logger.warning("Agent produced no result for task %s", task_id)

            # Let algorithm process the result and update props
            try:
                # Build fresh context after the agent ran
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
                            # Only set on children that don't already have props set
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
                    logger.warning("Failed to document work in knowledge base for task %s", task_id)

            logger.info("Agent run completed for task %s", task_id)

        except asyncio.CancelledError:
            logger.warning("Agent run cancelled for task %s", task_id)
        except Exception:
            logger.exception("Agent run failed for task %s", task_id)
        finally:
            self._active_runs.pop(task_id, None)

    async def wait_for_all(self, timeout: float | None = None) -> None:
        """Wait for all active agent runs to complete."""
        handles = [
            run.task_handle for run in self._active_runs.values()
            if run.task_handle is not None
        ]
        if handles:
            await asyncio.wait(handles, timeout=timeout)

    async def cancel_all(self) -> None:
        """Cancel all active agent runs."""
        for run in list(self._active_runs.values()):
            if run.task_handle and not run.task_handle.done():
                run.task_handle.cancel()
        await self.wait_for_all(timeout=5.0)
        self._active_runs.clear()

    def cleanup_stale(self, max_age_seconds: float = 3600) -> int:
        """Remove runs that have been active too long (likely stuck)."""
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
