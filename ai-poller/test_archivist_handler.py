"""Unit tests for archivist_handler — the knowledge-review scanner.

Mocks the ApiClient, so no backend is needed. Verifies the enqueue flow:
one archival WorkItem per unreviewed comment, the reviewed-flag idempotency
guard, the create-then-mark ordering, the unknown-task path, and that the
per-cycle batch cap is forwarded to the backend query. The persona load and
prompt build are real (cheap, hot-reloaded).
"""

from __future__ import annotations

import asyncio
import types
import unittest
from unittest import mock

from archivist_handler import ArchivistHandler, _payload_to_prompt_context
from chat_prompt import PromptPayload
from config import Config
from models import CommentEntity, TaskEntity
from persona_registry import CompiledPersona


def _comment(id: str, *, task_id="T-1", text="x", created_at=0, props=None,
             created_by="user") -> CommentEntity:
    return CommentEntity(
        id=id, task_id=task_id, text=text, created_at=created_at,
        created_by=created_by, props=props or {},
    )


def _task(id="T-1", parent_id=None) -> TaskEntity:
    return TaskEntity(id=id, parent_id=parent_id, title="Task", description="d", props={})


def _run(coro):
    return asyncio.run(coro)


class ArchivistEnqueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.api = mock.MagicMock()
        self.api.get_task.return_value = _task()
        self.api.list_comments.return_value = []
        self.api.create_work_item.return_value = types.SimpleNamespace(id="wi-1")
        self.config = Config(archivist_batch=7)
        self.handler = ArchivistHandler(api=self.api, config=self.config)

    def test_empty_no_action(self):
        self.api.list_comments_needing_archival.return_value = []
        self.assertEqual(_run(self.handler.run_cycle()), 0)
        self.api.create_work_item.assert_not_called()

    def test_forwards_batch_cap(self):
        self.api.list_comments_needing_archival.return_value = []
        _run(self.handler.run_cycle())
        self.api.list_comments_needing_archival.assert_called_once_with(limit=7)

    def test_enqueues_one_work_item_per_comment(self):
        self.api.list_comments_needing_archival.return_value = [
            _comment("c1"), _comment("c2", created_at=5),
        ]
        created = _run(self.handler.run_cycle())
        self.assertEqual(created, 2)
        self.assertEqual(self.api.create_work_item.call_count, 2)
        # Sweep-created items carry no triggering comment and target archivist.
        for call in self.api.create_work_item.call_args_list:
            self.assertEqual(call.kwargs["target_persona"], "archivist")
            self.assertIsNone(call.kwargs["triggering_comment_id"])

    def test_marks_reviewed_after_create_with_work_item_id(self):
        self.api.list_comments_needing_archival.return_value = [_comment("c1")]
        _run(self.handler.run_cycle())
        self.api.update_comment_props.assert_called_once()
        cid, patch = self.api.update_comment_props.call_args.args
        self.assertEqual(cid, "c1")
        self.assertTrue(patch["archivist-reviewed"])
        self.assertEqual(patch["archivist-work-item-id"], "wi-1")

    def test_skips_already_reviewed(self):
        c = _comment("c1", props={"archivist-reviewed": True})
        self.assertFalse(_run(self.handler._enqueue(c)))
        self.api.create_work_item.assert_not_called()
        self.api.update_comment_props.assert_not_called()

    def test_unknown_task_marks_reviewed_no_work_item(self):
        self.api.get_task.return_value = None
        c = _comment("c1")
        self.assertFalse(_run(self.handler._enqueue(c)))
        self.api.create_work_item.assert_not_called()
        # Marked reviewed so a dangling comment isn't retried forever.
        cid, patch = self.api.update_comment_props.call_args.args
        self.assertEqual(cid, "c1")
        self.assertTrue(patch["archivist-reviewed"])
        self.assertNotIn("archivist-work-item-id", patch)

    def test_create_failure_does_not_mark(self):
        # If the WorkItem create fails, the comment must stay unreviewed so the
        # next cycle retries it (no silent drop).
        self.api.list_comments_needing_archival.return_value = [_comment("c1")]
        self.api.create_work_item.side_effect = RuntimeError("boom")
        created = _run(self.handler.run_cycle())
        self.assertEqual(created, 0)
        self.api.update_comment_props.assert_not_called()

    def test_thread_excludes_the_trigger_comment(self):
        trigger = _comment("c1", text="trigger")
        other = _comment("c0", text="other", created_at=1)
        self.api.list_comments.return_value = [trigger, other]
        captured = {}
        self.api.create_work_item.side_effect = lambda **kw: captured.update(kw) or types.SimpleNamespace(id="wi-1")
        _run(self.handler._enqueue(trigger))
        user = captured["prompt_context"]["user"]
        # The trigger is rendered as the mention; the other comment is thread.
        self.assertIn("other", user)
        self.assertIn('triggering="true"', user)


class PayloadToPromptContextTest(unittest.TestCase):
    def _payload(self) -> PromptPayload:
        return PromptPayload(system="S", user="U", model="m", allowed_tools=["Bash(wp knowledge:*)"])

    def _persona(self, **o) -> CompiledPersona:
        d = dict(name="archivist", version=1, model="claude-sonnet-4-6",
                 tools=["Bash(wp knowledge:*)"], max_turns=40,
                 fixer_model="claude-sonnet-4-6")
        d.update(o)
        return CompiledPersona(**d)

    def test_shape(self):
        ctx = _payload_to_prompt_context(self._payload(), self._persona())
        for key in ("system", "user", "model", "allowed_tools", "max_turns",
                    "persona_name", "persona_version", "fixer_model"):
            self.assertIn(key, ctx)
        self.assertEqual(ctx["persona_name"], "archivist")
        self.assertEqual(ctx["fixer_model"], "claude-sonnet-4-6")


if __name__ == "__main__":
    unittest.main()
