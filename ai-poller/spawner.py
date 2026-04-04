"""Agent spawning — runs agents via the debate-based AgentRunner.

Every agent invocation is a multi-agent debate. The spawner doesn't know
or care — it calls runner.prompt() and gets back a synthesized result.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

from algorithm import Algorithm, SpawnPlan, TaskContext
from api_client import ApiClient
from config import Config
from debate import AgentRunner, DebateConfig
from knowledge import KnowledgeBase
from models import TaskEntity

logger = logging.getLogger(__name__)


@dataclass
class AgentRun:
    task_id: str
    algorithm_name: str
    started_at: float = field(default_factory=time.time)
    task_handle: asyncio.Task | None = None


class AgentSpawner:

    def __init__(self, api: ApiClient, config: Config) -> None:
        self._api = api
        self._config = config
        self._active_runs: dict[str, AgentRun] = {}

        proxy_url = os.environ.get("CLAUDE_PROXY_URL", "http://localhost:8400")
        proxy_key = os.environ.get("CLAUDE_PROXY_KEY", "")

        # Public backend URL for the proxy (which runs outside Railway)
        backend_host = os.environ.get("RAILWAY_SERVICE_BACKEND_URL", "")
        self._public_api_url = f"https://{backend_host}" if backend_host else self._config.api_url

        # Debate config from env or defaults
        self._runner = AgentRunner(
            proxy_url=proxy_url,
            proxy_key=proxy_key,
            config=DebateConfig(
                agents=int(os.environ.get("DEBATE_AGENTS", "2")),
                max_rounds=int(os.environ.get("DEBATE_MAX_ROUNDS", "10")),
                target_rounds=int(os.environ.get("DEBATE_TARGET_ROUNDS", "0")),
                timeout_minutes=int(os.environ.get("DEBATE_TIMEOUT_MINUTES", "30")),
            ),
        )

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
            logger.warning("Agent limit reached, cannot spawn for task %s", task.id)
            return

        # Guard against race condition: the poller builds TaskContext from a
        # snapshot fetched at the START of the cycle. If a previous agent posted
        # a proposal AFTER that snapshot was taken (but before this spawn call),
        # evaluate() would have seen zero pending proposals and returned a plan.
        # Re-checking fresh comments here prevents spawning a second planning
        # agent while one is already in-flight or has just posted its proposal.
        try:
            fresh_comments = self._api.list_comments(task.id)
            if any(
                c.comment_type == "PROPOSAL" and c.proposal_status == "PENDING"
                for c in fresh_comments
            ):
                logger.info(
                    "Task %s: fresh comment check found existing PENDING proposal — skipping spawn",
                    task.id,
                )
                return
        except Exception:
            logger.warning(
                "Task %s: failed fresh pending-proposal check; proceeding with spawn",
                task.id,
            )

        ai_status = task.props.get("aiStatus", "?")
        logger.info("Spawning %s agent for task '%s' (%s) [aiStatus=%s, runtime=%s, model=%s]",
                     algorithm.name, task.title, task.id, ai_status, plan.runtime or "default", plan.model)

        run = AgentRun(task_id=task.id, algorithm_name=algorithm.name)
        self._active_runs[task.id] = run
        run.task_handle = asyncio.create_task(
            self._run_agent(task, plan, algorithm, knowledge)
        )

    async def _run_agent(
        self,
        task: TaskEntity,
        plan: SpawnPlan,
        algorithm: Algorithm,
        knowledge: KnowledgeBase | None = None,
    ) -> None:
        task_id = task.id
        try:
            _, allowed_tools = plan.tools
            algo_tools = plan.metadata.get("algo_tools", [])

            prompt = (
                f"You have been assigned task {task_id}. "
                f"Begin by reviewing your task and any existing comments, "
                f"then take appropriate action based on your instructions."
            )

            # Run via debate-based runner
            result_text = await self._runner.prompt(
                prompt=prompt,
                system_prompt=plan.prompt,
                tools=plan.tools,
                model=plan.model,
                runtime=plan.runtime,
                fallbacks=[{"runtime": rec.runtime, "model": rec.model} for rec in plan.fallbacks],
                task_id=task_id,
                ai_status=task.props.get("aiStatus", ""),
                workplanner_api_url=self._public_api_url,
                internal_api_key=self._config.internal_api_key,
                algo_tools=algo_tools,
                max_turns=self._config.agent_limits.max_turns_per_run,
            )

            if result_text:
                logger.info("Agent result for task %s: %s", task_id, result_text[:500])
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
                                self._api.update_task(child.id, props=props_update.child_props)
            except Exception:
                logger.exception("Failed to run on_complete for task %s", task_id)

            # Document in knowledge base
            if knowledge and result_text:
                try:
                    knowledge.document_work(
                        task_id=task_id, agent_id=task_id,
                        work_type="agent_run", content=result_text[:2000])
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
        handles = [r.task_handle for r in self._active_runs.values() if r.task_handle]
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
        stale = [tid for tid, r in self._active_runs.items() if now - r.started_at > max_age_seconds]
        for tid in stale:
            run = self._active_runs.pop(tid)
            if run.task_handle and not run.task_handle.done():
                run.task_handle.cancel()
            logger.warning("Cleaned up stale agent run for task %s", tid)
        return len(stale)
