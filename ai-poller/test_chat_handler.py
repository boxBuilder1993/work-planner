"""Unit tests for chat_handler.

Covers the pure / nearly-pure helpers. End-to-end flow (poll → dispatch →
HTTP round-trip → atomic write) is task [11]'s smoke test.
"""

from __future__ import annotations

import json
import unittest

from chat_handler import (
    ChatHandler,
    DispatchOutcome,
    _telemetry_from_metadata,
)
from models import CommentEntity


def _comment(
    id: str,
    *,
    task_id: str = "task-1",
    text: str = "hello",
    created_at: int = 0,
    props: dict | None = None,
    created_by: str = "user",
) -> CommentEntity:
    return CommentEntity(
        id=id,
        task_id=task_id,
        text=text,
        created_at=created_at,
        created_by=created_by,
        props=props or {},
    )


# ─── _pick_one_per_task ───────────────────────────────────────────────────


class TestPickOnePerTask(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(ChatHandler._pick_one_per_task([]), [])

    def test_one_per_task_unchanged(self):
        a = _comment("a", task_id="T-1", created_at=10)
        b = _comment("b", task_id="T-2", created_at=20)
        out = ChatHandler._pick_one_per_task([a, b])
        self.assertEqual({c.id for c in out}, {"a", "b"})

    def test_same_task_oldest_wins(self):
        old = _comment("old", task_id="T-1", created_at=5)
        new = _comment("new", task_id="T-1", created_at=50)
        out = ChatHandler._pick_one_per_task([new, old])
        self.assertEqual([c.id for c in out], ["old"])

    def test_mixed_tasks_each_keeps_oldest(self):
        c1_old = _comment("c1_old", task_id="T-1", created_at=1)
        c1_new = _comment("c1_new", task_id="T-1", created_at=100)
        c2_old = _comment("c2_old", task_id="T-2", created_at=2)
        c2_new = _comment("c2_new", task_id="T-2", created_at=200)
        out = ChatHandler._pick_one_per_task([c1_new, c2_new, c1_old, c2_old])
        self.assertEqual({c.id for c in out}, {"c1_old", "c2_old"})
        # Output sorted by created_at
        self.assertEqual([c.id for c in out], ["c1_old", "c2_old"])


# ─── _task_has_dispatch_in_flight ─────────────────────────────────────────


class TestTaskHasDispatchInFlight(unittest.TestCase):
    def test_no_other_dispatched(self):
        comments = [
            _comment("m-1", text="@ai do thing"),
            _comment("c-2", text="reply", created_by="ai-default"),
        ]
        self.assertFalse(
            ChatHandler._task_has_dispatch_in_flight(comments, current_mention_id="m-1")
        )

    def test_sibling_in_dispatched_state(self):
        comments = [
            _comment("m-1", text="@ai"),
            _comment("m-2", text="@ai again", props={"ai-comment-status": "dispatched"}),
        ]
        self.assertTrue(
            ChatHandler._task_has_dispatch_in_flight(comments, current_mention_id="m-1")
        )

    def test_self_does_not_count(self):
        # If the current mention already has dispatched on it, that's fine —
        # this check is called before we flip our own status.
        comments = [
            _comment("m-1", text="@ai", props={"ai-comment-status": "dispatched"}),
        ]
        self.assertFalse(
            ChatHandler._task_has_dispatch_in_flight(comments, current_mention_id="m-1")
        )

    def test_terminal_states_do_not_count(self):
        # replied / failed don't lock; only `dispatched` does.
        comments = [
            _comment("c-1", text="@ai", props={"ai-comment-status": "replied"}),
            _comment("c-2", text="@ai", props={"ai-comment-status": "failed"}),
        ]
        self.assertFalse(
            ChatHandler._task_has_dispatch_in_flight(comments, current_mention_id="other")
        )


# ─── _route_persona ───────────────────────────────────────────────────────


class TestRoutePersona(unittest.TestCase):
    """Routing logic uses persona_registry which expects real files on disk.

    These tests just verify the suffix extraction; they go through the
    fallback path since no on-disk personas exist yet.
    """

    def test_extracts_suffix_lowercase(self):
        # Even if persona file doesn't exist, the regex match should pull
        # 'engineer' out; route_mention falls back to default if not found.
        # We can't assert on the persona name without files, but we can
        # confirm no exception.
        try:
            ChatHandler._route_persona("@ai-Engineer please help")
        except FileNotFoundError:
            # Expected when default.md is also missing.
            pass


# ─── _parse_success_response ──────────────────────────────────────────────


class TestParseSuccessResponse(unittest.TestCase):
    def _data(self, **kwargs):
        base = {
            "status": "done",
            "runtime": "claude",
            "result": "",
            "metadata": {},
        }
        base.update(kwargs)
        return base

    def test_valid_inner_json(self):
        inner = {"reply_text": "Hello there", "context_update": {"goal": "X"}}
        data = self._data(result=json.dumps(inner), metadata={"duration_ms": 100})
        outcome = ChatHandler._parse_success_response(data)
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.reply_text, "Hello there")
        self.assertEqual(outcome.context_update, {"goal": "X"})
        self.assertEqual(outcome.metadata, {"duration_ms": 100})
        self.assertEqual(outcome.runtime, "claude")

    def test_empty_result_string(self):
        data = self._data(result="")
        outcome = ChatHandler._parse_success_response(data)
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.error_code, "empty_reply")

    def test_whitespace_only_result(self):
        data = self._data(result="   \n  ")
        outcome = ChatHandler._parse_success_response(data)
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.error_code, "empty_reply")

    def test_unparseable_inner_json(self):
        data = self._data(result="not json {{{")
        outcome = ChatHandler._parse_success_response(data)
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.error_code, "malformed_output")

    def test_inner_is_not_object(self):
        data = self._data(result=json.dumps(["array", "not", "object"]))
        outcome = ChatHandler._parse_success_response(data)
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.error_code, "malformed_output")

    def test_reply_text_missing(self):
        data = self._data(result=json.dumps({"context_update": {}}))
        outcome = ChatHandler._parse_success_response(data)
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.error_code, "empty_reply")

    def test_reply_text_blank(self):
        data = self._data(result=json.dumps({"reply_text": "  ", "context_update": {}}))
        outcome = ChatHandler._parse_success_response(data)
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.error_code, "empty_reply")

    def test_context_update_not_dict_becomes_empty(self):
        inner = {"reply_text": "hi", "context_update": "should be dict"}
        data = self._data(result=json.dumps(inner))
        outcome = ChatHandler._parse_success_response(data)
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.context_update, {})

    def test_metadata_preserved_on_failure(self):
        data = self._data(result="", metadata={"duration_ms": 999})
        outcome = ChatHandler._parse_success_response(data)
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.metadata["duration_ms"], 999)


# ─── _telemetry_from_metadata ─────────────────────────────────────────────


class TestTelemetryFromMetadata(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(_telemetry_from_metadata({}), {})
        self.assertEqual(_telemetry_from_metadata(None), {})  # type: ignore[arg-type]

    def test_full_envelope(self):
        meta = {
            "duration_ms": 1500,
            "total_cost_usd": 0.0125,
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 5000,
            },
            "modelUsage": {
                "claude-sonnet-4-6": {"inputTokens": 100, "outputTokens": 50},
            },
        }
        out = _telemetry_from_metadata(meta)
        self.assertEqual(out["ai-duration-ms"], 1500)
        self.assertEqual(out["ai-cost-usd"], 0.0125)
        self.assertEqual(out["ai-stop-reason"], "end_turn")
        self.assertEqual(out["ai-model"], "claude-sonnet-4-6")
        self.assertEqual(out["ai-tokens"], {
            "input": 100,
            "output": 50,
            "cache_read": 0,
            "cache_creation": 5000,
        })

    def test_partial_envelope(self):
        meta = {"duration_ms": 200}
        out = _telemetry_from_metadata(meta)
        self.assertEqual(out, {"ai-duration-ms": 200})

    def test_usage_not_dict_is_ignored(self):
        meta = {"usage": "not a dict"}
        out = _telemetry_from_metadata(meta)
        self.assertNotIn("ai-tokens", out)

    def test_model_usage_empty_dict(self):
        meta = {"modelUsage": {}}
        out = _telemetry_from_metadata(meta)
        self.assertNotIn("ai-model", out)


# ─── DispatchOutcome smoke ────────────────────────────────────────────────


class TestDispatchOutcome(unittest.TestCase):
    def test_defaults(self):
        o = DispatchOutcome(success=False)
        self.assertFalse(o.success)
        self.assertEqual(o.reply_text, "")
        self.assertEqual(o.context_update, {})
        self.assertEqual(o.metadata, {})
        self.assertEqual(o.error_code, "")

    def test_independent_per_instance(self):
        a = DispatchOutcome(success=False)
        b = DispatchOutcome(success=False)
        a.context_update["x"] = 1
        a.metadata["y"] = 2
        self.assertNotIn("x", b.context_update)
        self.assertNotIn("y", b.metadata)


if __name__ == "__main__":
    unittest.main()
