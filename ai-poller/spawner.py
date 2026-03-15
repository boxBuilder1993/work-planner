"""Agent spawning — launches Claude Agent SDK sub-agents for tasks.

Handles agent lifecycle: spawn, monitor, timeout, cleanup.
Respects concurrency limits from config.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
)

from api_client import ApiClient
from config import Config
from hierarchy import AgentRole, generate_prompt, get_tools_for_role
from knowledge import KnowledgeBase
from task_tools import set_api_client, create_workplanner_mcp_server

logger = logging.getLogger(__name__)


@dataclass
class AgentRun:
    """Tracks a single agent run."""
    task_id: str
    role: str
    started_at: float = field(default_factory=time.time)
    task_handle: asyncio.Task | None = None


class AgentSpawner:
    """Manages spawning and tracking of Claude agent sub-processes."""

    def __init__(self, api: ApiClient, config: Config, knowledge: KnowledgeBase | None = None) -> None:
        self._api = api
        self._config = config
        self._knowledge = knowledge
        self._active_runs: dict[str, AgentRun] = {}  # task_id -> AgentRun

    @property
    def active_count(self) -> int:
        return len(self._active_runs)

    def is_running(self, task_id: str) -> bool:
        return task_id in self._active_runs

    def can_spawn(self) -> bool:
        return self.active_count < self._config.agent_limits.max_global_agents

    async def spawn_agent(self, role: AgentRole) -> None:
        """Spawn a Claude agent for the given task/role.

        The agent runs asynchronously and its results are posted back
        to the backend via the MCP tools.
        """
        task = role.task

        if self.is_running(task.id):
            logger.warning("Agent already running for task %s, skipping", task.id)
            return

        if not self.can_spawn():
            logger.warning("Agent limit reached (%d), cannot spawn for task %s",
                           self._config.agent_limits.max_global_agents, task.id)
            return

        logger.info("Spawning %s agent for task '%s' (%s)", role.role_name, task.title, task.id)

        # Build the system prompt with knowledge context
        system_prompt = generate_prompt(role)
        if self._knowledge:
            context = self._knowledge.query_knowledge(
                f"context for: {task.title} {task.description}",
                limit=3,
            )
            if context:
                knowledge_section = "\n\nRelevant knowledge from previous work:\n"
                for doc in context:
                    knowledge_section += f"- {doc['document'][:200]}\n"
                system_prompt += knowledge_section

        # Get tool assignment
        mcp_servers, allowed_tools = get_tools_for_role(
            role,
            github_token=os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", ""),
        )

        # Create the agent run record
        run = AgentRun(task_id=task.id, role=role.role_name)
        self._active_runs[task.id] = run

        # Launch the agent as an async task
        run.task_handle = asyncio.create_task(
            self._run_agent(task.id, system_prompt, mcp_servers, allowed_tools)
        )

    async def _run_agent(
        self,
        task_id: str,
        system_prompt: str,
        extra_mcp_servers: dict,
        allowed_tools: list[str],
    ) -> None:
        """Execute one agent run for a task."""
        try:
            set_api_client(self._api)
            workplanner_mcp = create_workplanner_mcp_server()

            mcp_servers = {"workplanner": workplanner_mcp}
            mcp_servers.update(extra_mcp_servers)

            prompt = (
                f"You have been assigned task {task_id}. "
                f"Begin by reviewing your task and any existing comments, "
                f"then take appropriate action based on your role."
            )

            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                mcp_servers=mcp_servers,
                allowed_tools=allowed_tools,
                max_turns=self._config.agent_limits.max_turns_per_run,
                model="claude-sonnet-4-6",
                env={"ANTHROPIC_API_KEY": self._config.anthropic_api_key},
            )

            result_text = ""
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                async for message in client.receive_response():
                    if isinstance(message, ResultMessage) and message.subtype == "success":
                        result_text = message.result

            # Document the agent's work in the knowledge base
            if self._knowledge and result_text:
                self._knowledge.document_work(
                    task_id=task_id,
                    agent_id=task_id,
                    work_type="agent_run",
                    content=result_text[:2000],
                )

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
        # Wait briefly for cancellations
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
