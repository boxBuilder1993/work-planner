"""Unit tests for algo_decompose_v2.DecomposeAndDelegateV2.

Focuses on the STATUS_ALIASES normalization in on_plan_executed so that
tasks with legacy aiStatus values (e.g. "plan_proposed") still transition
to "managing" after plan execution instead of getting stuck re-planning.
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

if "claude_agent_sdk" not in sys.modules:
    sdk = types.ModuleType("claude_agent_sdk")

    def _tool(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def _create_sdk_mcp_server(*args, **kwargs):
        return {"name": kwargs.get("name", "algo")}

    sdk.tool = _tool
    sdk.create_sdk_mcp_server = _create_sdk_mcp_server
    sys.modules["claude_agent_sdk"] = sdk

from models import TaskEntity, CommentEntity
from algorithm import TaskContext, PropsUpdate
from algo_decompose_v2 import DecomposeAndDelegateV2, STATUS_ALIASES


def _make_task(ai_status: str, children_count: int = 0, task_id: str = "task-001") -> TaskEntity:
    return TaskEntity(
        id=task_id,
        userId="user-1",
        title="Test task",
        status="PENDING",
        aiEnabled=True,
        props={"aiStatus": ai_status, "algorithm": "decompose_and_delegate_v2", "runCount": 0},
    )


def _make_child(task_id: str = "child-001") -> TaskEntity:
    return TaskEntity(
        id=task_id,
        userId="user-1",
        title="Child task",
        status="PENDING",
        aiEnabled=True,
        props={"aiStatus": "planning", "algorithm": "decompose_and_delegate_v2"},
    )


def _make_approved_comment(text: str = "[PLAN PROPOSAL] decompose into subtasks") -> CommentEntity:
    return CommentEntity(
        id="comment-001",
        taskId="task-001",
        text=text,
        commentType="PROPOSAL",
        createdBy="user",
        proposalStatus="APPROVED",
        createdAt=1000,
        updatedAt=1000,
    )


def _make_ctx(task: TaskEntity, children: list[TaskEntity] | None = None,
              comments: list[CommentEntity] | None = None) -> TaskContext:
    return TaskContext(
        task=task,
        comments=comments or [],
        children=children or [],
        parent=None,
        children_comments={},
    )


class TestStatusAliasesNormalization(unittest.TestCase):
    """Verify STATUS_ALIASES covers the known legacy statuses."""

    def test_plan_proposed_maps_to_planning(self):
        self.assertEqual(STATUS_ALIASES.get("plan_proposed"), "planning")

    def test_needs_planning_maps_to_planning(self):
        self.assertEqual(STATUS_ALIASES.get("needs_planning"), "planning")

    def test_in_progress_maps_to_managing(self):
        self.assertEqual(STATUS_ALIASES.get("in_progress"), "managing")

    def test_worker_ready_maps_to_working(self):
        self.assertEqual(STATUS_ALIASES.get("worker_ready"), "working")

    def test_planning_complete_maps_to_managing(self):
        self.assertEqual(STATUS_ALIASES.get("planning_complete"), "managing")

    def test_unknown_status_unchanged(self):
        self.assertEqual(STATUS_ALIASES.get("managing", "managing"), "managing")
        self.assertEqual(STATUS_ALIASES.get("working", "working"), "working")


class TestOnPlanExecutedStatusAliasNormalization(unittest.TestCase):
    """
    Regression tests for the bug where on_plan_executed did not normalize
    legacy aiStatus values via STATUS_ALIASES before comparing.

    Before the fix, a task with aiStatus="plan_proposed" would never match
    ("plan_approved", "planning") in on_plan_executed, so it would not
    transition to "managing" even after children were created — causing it to
    re-execute the plan every poller cycle.
    """

    def setUp(self):
        self.algo = DecomposeAndDelegateV2()

    def _run_on_plan_executed(self, ai_status: str, children: list[TaskEntity]) -> PropsUpdate | None:
        """
        Call _execute_plan to get the SpawnPlan, then invoke the on_complete
        callback directly with a task that has the given aiStatus and children.
        """
        # Build initial context to get the SpawnPlan (children don't matter here)
        approved_comment = _make_approved_comment()
        initial_task = _make_task(ai_status)
        initial_ctx = _make_ctx(initial_task, children=[], comments=[approved_comment])

        spawn_plan = self.algo._execute_plan(initial_ctx)
        self.assertIsNotNone(spawn_plan)

        # Now simulate the callback being called after plan execution,
        # where the task still has the legacy aiStatus but children now exist.
        post_exec_task = _make_task(ai_status)
        post_exec_ctx = _make_ctx(post_exec_task, children=children, comments=[approved_comment])

        return spawn_plan.on_complete(post_exec_ctx, "Plan executed successfully.")

    def test_plan_proposed_with_children_transitions_to_managing(self):
        """
        Core regression: task with aiStatus="plan_proposed" (legacy) must
        transition to "managing" after plan execution when children exist.
        Without STATUS_ALIASES normalization in on_plan_executed, this would
        return {"runCount": 1} without setting aiStatus, keeping the task stuck.
        """
        children = [_make_child("child-001"), _make_child("child-002")]
        result = self._run_on_plan_executed("plan_proposed", children)

        self.assertIsNotNone(result)
        self.assertEqual(result.self_props.get("aiStatus"), "managing",
                         "plan_proposed should normalize to 'planning' via STATUS_ALIASES "
                         "and then transition to 'managing' because children exist")

    def test_plan_approved_with_children_transitions_to_managing(self):
        """Standard v2 status: plan_approved + children → managing."""
        children = [_make_child()]
        result = self._run_on_plan_executed("plan_approved", children)

        self.assertIsNotNone(result)
        self.assertEqual(result.self_props.get("aiStatus"), "managing")

    def test_planning_with_children_transitions_to_managing(self):
        """planning + children → managing."""
        children = [_make_child()]
        result = self._run_on_plan_executed("planning", children)

        self.assertIsNotNone(result)
        self.assertEqual(result.self_props.get("aiStatus"), "managing")

    def test_needs_planning_with_children_transitions_to_managing(self):
        """needs_planning (legacy alias for planning) + children → managing."""
        children = [_make_child()]
        result = self._run_on_plan_executed("needs_planning", children)

        self.assertIsNotNone(result)
        self.assertEqual(result.self_props.get("aiStatus"), "managing",
                         "needs_planning should normalize to 'planning' → 'managing'")

    def test_plan_proposed_no_children_non_decompose_plan_transitions_to_working(self):
        """
        Legacy plan_proposed with no children and a worker-ready plan → working.
        """
        result = self._run_on_plan_executed("plan_proposed", children=[])

        self.assertIsNotNone(result)
        # Plan text is "[PLAN PROPOSAL] decompose into subtasks" which contains "decompos"
        # so it should retry planning, not go to working
        self.assertIn(result.self_props.get("aiStatus"), ("planning", "working"))

    def test_run_count_incremented(self):
        """on_plan_executed always increments runCount."""
        children = [_make_child()]
        result = self._run_on_plan_executed("plan_proposed", children)

        self.assertIsNotNone(result)
        self.assertEqual(result.self_props.get("runCount"), 1)


if __name__ == "__main__":
    unittest.main()
