"""Agent spawning — submits jobs to the Claude proxy and polls for results.

The proxy runs claude -p on the user's Mac with their subscription auth.
Uses async job queue: POST /run → job_id, GET /status/{job_id} → result.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

import requests

from algorithm import Algorithm, SpawnPlan, TaskContext
from api_client import ApiClient
from config import Config
from knowledge import KnowledgeBase
from models import TaskEntity

logger = logging.getLogger(__name__)

POLL_INTERVAL = 10  # seconds between status checks
JOB_TIMEOUT = 600   # max seconds to wait for a job


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
        self._proxy_url = os.environ.get("CLAUDE_PROXY_URL", "http://localhost:8400")
        self._proxy_key = os.environ.get("CLAUDE_PROXY_KEY", "")
        # Public backend URL for the proxy (which runs outside Railway)
        backend_host = os.environ.get("RAILWAY_SERVICE_BACKEND_URL", "")
        self._public_api_url = f"https://{backend_host}" if backend_host else self._config.api_url

    @property
    def active_count(self) -> int:
        return len(self._active_runs)

    def is_running(self, task_id: str) -> bool:
        return task_id in self._active_runs

    def can_spawn(self) -> bool:
        return self.active_count < self._config.agent_limits.max_global_agents

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._proxy_key:
            h["X-Proxy-Key"] = self._proxy_key
        return h

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

        ai_status = task.props.get("aiStatus", "needs_planning")
        logger.info("Spawning %s agent for task '%s' (%s) [aiStatus=%s, model=%s]",
                     algorithm.name, task.title, task.id, ai_status, plan.model)

        # Enrich prompt with knowledge
        system_prompt = plan.prompt
        if knowledge:
            try:
                context = knowledge.query_knowledge(
                    f"context for: {task.title} {task.description}", limit=3)
                if context:
                    system_prompt += "\n\nRelevant knowledge from previous work:\n"
                    for doc in context:
                        system_prompt += f"- {doc['document'][:200]}\n"
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
            _, allowed_tools = plan.tools
            algo_tools = plan.metadata.get("algo_tools", [])

            prompt = (
                f"You have been assigned task {task_id}. "
                f"Begin by reviewing your task and any existing comments, "
                f"then take appropriate action based on your instructions."
            )

            request_body = {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "model": plan.model,
                "max_turns": self._config.agent_limits.max_turns_per_run,
                "allowed_tools": allowed_tools,
                "algo_tools": algo_tools,
                "task_id": task_id,
                "ai_status": task.props.get("aiStatus", ""),
                "workplanner_api_url": self._public_api_url,
                "internal_api_key": self._config.internal_api_key,
            }

            # Submit job
            logger.info("Submitting job for task %s to proxy", task_id)
            loop = asyncio.get_event_loop()
            submit_resp = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self._proxy_url}/run",
                    json=request_body,
                    headers=self._headers(),
                    timeout=30,
                ),
            )

            if submit_resp.status_code != 200:
                logger.error("Proxy submit error for task %s: %d %s",
                             task_id, submit_resp.status_code, submit_resp.text[:500])
                return

            job_id = submit_resp.json().get("job_id")
            if not job_id:
                logger.error("No job_id returned for task %s", task_id)
                return

            logger.info("Job %s submitted for task %s, polling for result...", job_id, task_id)

            # Poll for result
            result_text = ""
            success = False
            start = time.time()

            while time.time() - start < JOB_TIMEOUT:
                await asyncio.sleep(POLL_INTERVAL)

                status_resp = await loop.run_in_executor(
                    None,
                    lambda: requests.get(
                        f"{self._proxy_url}/status/{job_id}",
                        headers=self._headers(),
                        timeout=15,
                    ),
                )

                if status_resp.status_code != 200:
                    logger.warning("Poll error for job %s: %d", job_id, status_resp.status_code)
                    continue

                data = status_resp.json()
                status = data.get("status")

                if status == "done":
                    result_text = data.get("result", "")
                    success = True
                    logger.info("Job %s done for task %s: %s", job_id, task_id, result_text[:300])
                    break
                elif status == "error":
                    logger.error("Job %s failed for task %s: %s",
                                 job_id, task_id, data.get("error", "")[:500])
                    break
                # else: queued or running, keep polling

            if not success and not result_text:
                elapsed = time.time() - start
                if elapsed >= JOB_TIMEOUT:
                    logger.error("Job %s timed out after %ds for task %s", job_id, JOB_TIMEOUT, task_id)
                # Either timed out or errored — result_text stays empty

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
