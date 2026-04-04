"""Unit tests for SDLC state normalization and fallback transitions."""

from __future__ import annotations

import sys
import types
import unittest

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

from algo_sdlc import SDLC
from algorithm import TaskContext, PropsUpdate
from models import CommentEntity, TaskEntity


def _make_task(
    ai_status: str,
    *,
    task_id: str = "task-001",
    parent_id: str | None = "parent-001",
    extra_props: dict | None = None,
) -> TaskEntity:
    props = {"aiStatus": ai_status, "algorithm": "sdlc", "runCount": 0}
    if extra_props:
        props.update(extra_props)
    return TaskEntity(
        id=task_id,
        userId="user-1",
        parentId=parent_id,
        title="Test task",
        status="PENDING",
        aiEnabled=True,
        props=props,
    )


def _make_child(task_id: str = "child-001", *, ai_status: str = "proof_submitted", status: str = "PENDING") -> TaskEntity:
    return TaskEntity(
        id=task_id,
        userId="user-1",
        parentId="task-001",
        title="Child task",
        status=status,
        aiEnabled=True,
        props={"aiStatus": ai_status, "algorithm": "sdlc"},
    )


def _make_comment(
    *,
    status: str,
    text: str = "[PLAN PROPOSAL] do the thing",
    created_at: int = 1000,
) -> CommentEntity:
    return CommentEntity(
        id=f"comment-{created_at}",
        taskId="task-001",
        text=text,
        commentType="PROPOSAL",
        createdBy="task-001",
        proposalStatus=status,
        createdAt=created_at,
        updatedAt=created_at,
    )


def _make_ctx(
    task: TaskEntity,
    *,
    comments: list[CommentEntity] | None = None,
    children: list[TaskEntity] | None = None,
) -> TaskContext:
    children = children or []
    return TaskContext(
        task=task,
        comments=comments or [],
        children=children,
        parent=None,
        children_comments={child.id: [] for child in children},
    )


class TestSDLCRuntimeFallbacks(unittest.TestCase):
    def setUp(self) -> None:
        self.algo = SDLC()

    def test_execute_fallback_normalizes_legacy_status_to_manage(self):
        approved = _make_comment(status="APPROVED")
        initial_ctx = _make_ctx(_make_task("plan_approved"), comments=[approved])
        plan = self.algo._execute(initial_ctx)

        post_ctx = _make_ctx(
            _make_task("plan_approved"),
            comments=[approved],
            children=[_make_child(status="PENDING", ai_status="propose")],
        )
        result = plan.on_complete(post_ctx, "done")

        self.assertIsNotNone(result)
        self.assertEqual(result.self_props.get("aiStatus"), "manage")
        self.assertEqual(result.self_props.get("lastExecutedApprovalTs"), 1000)

    def test_manage_fallback_normalizes_in_progress_to_done(self):
        child = _make_child(status="CLOSED")
        ctx = _make_ctx(_make_task("in_progress"), children=[child])
        plan = self.algo._manage(ctx)

        self.assertIsNotNone(plan)
        result = plan.on_complete(ctx, "done")

        self.assertIsNotNone(result)
        self.assertEqual(result.self_props.get("aiStatus"), "done")

    def test_awaiting_input_resume_execute_returns_execute_plan(self):
        approved = _make_comment(status="APPROVED")
        task = _make_task("awaiting_input", extra_props={"resumeState": "work_approved"})
        ctx = _make_ctx(task, comments=[approved])

        plan = self.algo.evaluate(ctx, is_running=False)

        self.assertIsNotNone(plan)
        self.assertIn("Approved action:", plan.prompt)

    def test_awaiting_input_resume_manage_returns_manage_plan(self):
        resolved_question = _make_comment(status="DENIED", text="[QUESTION] what now?")
        task = _make_task("awaiting_input", extra_props={"resumeState": "in_progress"})
        ctx = _make_ctx(task, comments=[resolved_question], children=[_make_child(status="CLOSED")])

        plan = self.algo.evaluate(ctx, is_running=False)

        self.assertIsNotNone(plan)
        self.assertIn("You are the manager of task:", plan.prompt)


if __name__ == "__main__":
    unittest.main()
