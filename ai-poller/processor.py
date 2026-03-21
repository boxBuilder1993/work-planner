"""Core processing logic for the AI poller.

Dispatches ai-enabled tasks to algorithm handlers. Each algorithm
controls its own lifecycle via the SpawnPlan interface.
"""

from __future__ import annotations

import logging

from algo_decompose import DecomposeAndDelegate
from algo_simple_answer import SimpleAnswer
from algorithm import AlgorithmRegistry, TaskContext
from api_client import ApiClient
from config import Config
from knowledge import KnowledgeBase, KnowledgeBaseFactory
from models import TaskEntity
from spawner import AgentSpawner

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Algorithm registry setup
# ---------------------------------------------------------------------------

def build_registry() -> AlgorithmRegistry:
    registry = AlgorithmRegistry()
    registry.register(SimpleAnswer())
    registry.register(DecomposeAndDelegate())
    registry.set_default("simple_answer")
    return registry


# ---------------------------------------------------------------------------
# Main poll cycle processor
# ---------------------------------------------------------------------------

class PollCycleProcessor:
    """Orchestrates one full poll cycle."""

    def __init__(
        self,
        api: ApiClient,
        config: Config,
        spawner: AgentSpawner,
        knowledge_factory: KnowledgeBaseFactory | None = None,
    ) -> None:
        self._api = api
        self._config = config
        self._spawner = spawner
        self._knowledge_factory = knowledge_factory
        self._registry = build_registry()

    async def run_cycle(self) -> int:
        """Run one poll cycle. Returns the number of actions taken."""
        self._spawner.cleanup_stale()

        # Fetch all tasks
        tasks = self._api.get_all_tasks()
        if not tasks:
            return 0

        tasks_by_id = {t.id: t for t in tasks}

        # Filter to ai-enabled, open tasks
        ai_tasks = [t for t in tasks if t.ai_enabled and t.status != "CLOSED"]
        logger.info("Found %d total tasks, %d ai_enabled & open", len(tasks), len(ai_tasks))

        if not ai_tasks:
            return 0

        # Fetch comments for all ai tasks
        all_comments_map: dict[str, list] = {}
        for t in ai_tasks:
            all_comments_map[t.id] = self._api.list_comments(t.id)

        actions = 0

        for task in ai_tasks:
            if not self._spawner.can_spawn():
                logger.info("Agent limit reached, deferring remaining tasks")
                break

            # Build context
            comments = all_comments_map.get(task.id, [])
            children = [t for t in tasks if t.parent_id == task.id]
            parent = tasks_by_id.get(task.parent_id) if task.parent_id else None

            ctx = TaskContext(
                task=task,
                comments=comments,
                children=children,
                parent=parent,
            )

            # Look up algorithm
            algo_name = task.props.get("algorithm", "simple_answer")
            algorithm = self._registry.get(algo_name)

            # Initialize props for new ai-enabled tasks
            if not task.props.get("aiStatus"):
                logger.info("Initializing props for task '%s' with algorithm '%s'", task.title, algo_name)
                self._api.update_task(task.id, props={"algorithm": algo_name, "aiStatus": "needs_planning"})
                # Update local task object
                task.props["algorithm"] = algo_name
                task.props["aiStatus"] = "needs_planning"

            is_running = self._spawner.is_running(task.id)
            plan = algorithm.evaluate(ctx, is_running)

            if plan is None:
                ai_status = task.props.get("aiStatus", "?")
                logger.info("Task '%s' [%s/%s]: no action needed", task.title, algo_name, ai_status)
                continue

            # Resolve knowledge base
            knowledge: KnowledgeBase | None = None
            if self._knowledge_factory and task.user_id:
                try:
                    knowledge = self._knowledge_factory.for_user(task.user_id)
                except Exception:
                    logger.warning("Failed to init knowledge base for user %s", task.user_id)

            ai_status = task.props.get("aiStatus", "?")
            logger.info("Task '%s' [%s/%s]: spawning agent", task.title, algo_name, ai_status)
            await self._spawner.spawn(task, plan, algorithm, knowledge)
            actions += 1

        return actions
