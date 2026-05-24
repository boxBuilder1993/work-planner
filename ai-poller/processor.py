"""Core processing logic for the AI poller.

Dispatches ai-enabled tasks to algorithm handlers. Each algorithm
controls its own lifecycle via the SpawnPlan interface.
"""

from __future__ import annotations

import logging

from algo_decompose import DecomposeAndDelegate
from algo_decompose_v2 import DecomposeAndDelegateV2
from algo_orchestrated import Orchestrated
from algo_sdlc import SDLC
from algo_simple_answer import SimpleAnswer
from algorithm import AlgorithmRegistry, TaskContext
from api_client import ApiClient
from chat_handler import ChatHandler
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
    registry.register(DecomposeAndDelegateV2())
    registry.register(SDLC())
    registry.register(Orchestrated())
    registry.set_default("orchestrated")
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
        # Built eagerly — cheap, idle when ENABLE_CHAT_HANDLER is false.
        self._chat_handler = ChatHandler(api=api, config=config)

    async def run_cycle(self) -> int:
        """Run one poll cycle. Returns the number of actions taken.

        When `config.enable_chat_handler` is True, legacy algorithm dispatch
        is fully bypassed and the chat-mention handler runs instead. The
        chat handler currently no-ops; full implementation is task [5] in
        the chat-poller refocus (see docs/CHAT_DESIGN.md).
        """
        if self._config.enable_chat_handler:
            return await self._run_chat_cycle()
        return await self._run_legacy_cycle()

    async def _run_chat_cycle(self) -> int:
        """Chat-mention dispatch path. Delegates to ChatHandler.run_cycle()."""
        return await self._chat_handler.run_cycle()

    async def _run_legacy_cycle(self) -> int:
        """Legacy algorithm dispatch path (SDLC / orchestrated / etc.).

        Kept intact to preserve the rollback path: setting
        ENABLE_CHAT_HANDLER=false restores the original behavior.
        """
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

            # Fetch children's comments for manager to review proposals
            children_comments: dict[str, list] = {}
            for child in children:
                if child.id in all_comments_map:
                    children_comments[child.id] = all_comments_map[child.id]
                else:
                    children_comments[child.id] = self._api.list_comments(child.id)

            # Build full ancestor chain (root → parent) from in-memory map
            ancestors: list = []
            cursor = parent
            while cursor:
                ancestors.append(cursor)
                cursor = tasks_by_id.get(cursor.parent_id) if cursor.parent_id else None
            ancestors.reverse()

            ctx = TaskContext(
                task=task,
                comments=comments,
                children=children,
                parent=parent,
                children_comments=children_comments,
                ancestors=ancestors,
            )

            # Look up algorithm
            algo_name = task.props.get("algorithm", "orchestrated")
            algorithm = self._registry.get(algo_name)

            # Let the algorithm handle its own initialization
            init_update = algorithm.initialize(ctx)
            if init_update and init_update.self_props:
                logger.info("Task '%s': initialize → %s", task.title, init_update.self_props)
                self._api.update_task(task.id, props=init_update.self_props)
                task.props.update(init_update.self_props)
                # Re-resolve algorithm if it changed
                if "algorithm" in init_update.self_props:
                    algo_name = init_update.self_props["algorithm"]
                    algorithm = self._registry.get(algo_name)

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

            # Orchestrator plans are subject to their own concurrent limit
            if plan.is_orchestrator and not self._spawner.can_spawn_orchestrator():
                logger.info(
                    "Task '%s' [%s/%s]: orchestrator limit reached, deferring",
                    task.title, algo_name, ai_status,
                )
                continue

            logger.info("Task '%s' [%s/%s]: spawning agent", task.title, algo_name, ai_status)
            await self._spawner.spawn(task, plan, algorithm, knowledge)
            actions += 1

        return actions
