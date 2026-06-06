"""Unit tests for work_item_handler — the WorkItem dispatcher.

Covers the pure helpers (proxy response parsing, telemetry shaping). The
HTTP / state-machine wiring is covered by the backend tests and the
manual smoke-test in Phase 1.
"""

from __future__ import annotations

import unittest
from unittest import mock

from config import Config
from models import WorkItemEntity
from work_item_handler import (
    DEFAULT_FIXER_MODEL,
    DispatchOutcome,
    WorkItemHandler,
    _parse_proxy_done,
    _parse_result_str,
    _strip_code_fences,
    _telemetry_props,
)


class TestParseProxyDone(unittest.TestCase):
    """`data["result"]` is a JSON string the AI emitted; parses to
    `{reply_text, artifacts?, context_update?}`."""

    def _build(self, result_str: str, runtime: str = "claude", metadata: dict | None = None) -> dict:
        return {
            "status": "done",
            "result": result_str,
            "runtime": runtime,
            "metadata": metadata or {},
        }

    def test_valid_reply_returns_success(self):
        out = _parse_proxy_done(self._build('{"reply_text": "hi", "artifacts": {}}'))
        self.assertTrue(out.success)
        self.assertEqual(out.output["reply_text"], "hi")
        self.assertEqual(out.runtime, "claude")

    def test_empty_result_string_is_failure(self):
        out = _parse_proxy_done(self._build(""))
        self.assertFalse(out.success)
        self.assertIn("empty", out.error.lower())

    def test_unparseable_json_is_failure(self):
        out = _parse_proxy_done(self._build("not json at all"))
        self.assertFalse(out.success)
        self.assertIn("parse", out.error.lower())

    def test_non_object_inner_is_failure(self):
        out = _parse_proxy_done(self._build('["a", "b"]'))
        self.assertFalse(out.success)
        self.assertIn("not a JSON object", out.error)

    def test_missing_reply_text_is_failure(self):
        out = _parse_proxy_done(self._build('{"artifacts": {}}'))
        self.assertFalse(out.success)
        self.assertIn("reply_text", out.error)

    def test_empty_reply_text_is_failure(self):
        out = _parse_proxy_done(self._build('{"reply_text": "  "}'))
        self.assertFalse(out.success)

    def test_metadata_propagated_on_success(self):
        meta = {"duration_ms": 1500, "total_cost_usd": 0.04}
        out = _parse_proxy_done(
            self._build('{"reply_text": "hi"}', metadata=meta)
        )
        self.assertTrue(out.success)
        self.assertEqual(out.metadata, meta)

    def test_metadata_propagated_on_failure(self):
        # Even failed responses keep the metadata for telemetry purposes.
        meta = {"duration_ms": 999}
        out = _parse_proxy_done(self._build("garbage", metadata=meta))
        self.assertFalse(out.success)
        self.assertEqual(out.metadata, meta)

    def test_extras_in_inner_are_preserved(self):
        out = _parse_proxy_done(self._build(
            '{"reply_text": "hi", "artifacts": {"branch": "X"}, "context_update": {"k": "v"}}'
        ))
        self.assertTrue(out.success)
        self.assertEqual(out.output["artifacts"]["branch"], "X")
        self.assertEqual(out.output["context_update"]["k"], "v")


class TestTelemetryProps(unittest.TestCase):
    """Shape we put on the reply comment's props so UI/CLI telemetry
    consumers built against the old chat_handler still work."""

    def test_empty_metadata_returns_empty(self):
        self.assertEqual(_telemetry_props({}), {})

    def test_extracts_duration_cost_stop_reason(self):
        out = _telemetry_props({
            "duration_ms": 1234,
            "total_cost_usd": 0.5,
            "stop_reason": "end_turn",
        })
        self.assertEqual(out["ai-duration-ms"], 1234)
        self.assertEqual(out["ai-cost-usd"], 0.5)
        self.assertEqual(out["ai-stop-reason"], "end_turn")

    def test_extracts_usage_tokens(self):
        out = _telemetry_props({
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 900,
                "cache_creation_input_tokens": 200,
            },
        })
        self.assertEqual(out["ai-tokens"], {
            "input": 100, "output": 50,
            "cache_read": 900, "cache_creation": 200,
        })

    def test_extracts_model_from_model_usage(self):
        out = _telemetry_props({
            "modelUsage": {"claude-sonnet-4-6": {"input_tokens": 100}},
        })
        self.assertEqual(out["ai-model"], "claude-sonnet-4-6")

    def test_missing_keys_skipped_silently(self):
        out = _telemetry_props({"duration_ms": 5})
        self.assertEqual(out, {"ai-duration-ms": 5})
        self.assertNotIn("ai-cost-usd", out)


class TestParseResultStrFixerFailure(unittest.TestCase):
    """The fixer signals an explicit failure via {"_fixer_failed": true,
    "reason": "..."}. The parser preserves that so _invoke_proxy can surface
    a clear error (rather than the generic "reply_text missing" message)."""

    def test_fixer_failed_marker_returns_success_with_marker(self):
        # Important: _parse_result_str returns success=True so the caller
        # (_invoke_proxy) can detect the marker and route to its own
        # failure path with the right error message. The marker is its own
        # contract; the strict-parse step just transports it.
        out = _parse_result_str(
            '{"_fixer_failed": true, "reason": "no recoverable content"}',
            runtime="claude", metadata={},
        )
        self.assertTrue(out.success)
        self.assertTrue(out.output.get("_fixer_failed"))
        self.assertIn("no recoverable", out.output.get("reason", ""))


class TestParseProxyDoneBackCompat(unittest.TestCase):
    """The old _parse_proxy_done(data) shape — kept as a shim so the rest
    of the tests in this file still type-check. New code paths use
    _parse_result_str directly."""

    def test_shim_unwraps_data_dict(self):
        out = _parse_proxy_done({
            "status": "done",
            "result": '{"reply_text": "hi"}',
            "runtime": "claude",
            "metadata": {"duration_ms": 5},
        })
        self.assertTrue(out.success)
        self.assertEqual(out.output["reply_text"], "hi")
        self.assertEqual(out.runtime, "claude")
        self.assertEqual(out.metadata, {"duration_ms": 5})


class TestFenceStripping(unittest.TestCase):
    """The fixer is the sole JSON parse point now, so _parse_result_str must
    tolerate a fenced ```json block (a fixer fence would otherwise fail all
    retries)."""

    def test_plain_json_unchanged(self):
        out = _parse_result_str('{"reply_text": "hi"}')
        self.assertTrue(out.success)
        self.assertEqual(out.output["reply_text"], "hi")

    def test_json_fence_stripped(self):
        out = _parse_result_str('```json\n{"reply_text": "hi"}\n```')
        self.assertTrue(out.success, out.error)
        self.assertEqual(out.output["reply_text"], "hi")

    def test_bare_fence_stripped(self):
        out = _parse_result_str('```\n{"reply_text": "hi"}\n```')
        self.assertTrue(out.success, out.error)
        self.assertEqual(out.output["reply_text"], "hi")

    def test_strip_helper_leaves_unfenced(self):
        self.assertEqual(_strip_code_fences('{"a":1}'), '{"a":1}')
        self.assertEqual(_strip_code_fences('```json\n{"a":1}\n```'), '{"a":1}')

    def test_default_fixer_model_configured(self):
        # The fixer always runs; a default model must exist for personas that
        # don't override it.
        self.assertTrue(DEFAULT_FIXER_MODEL)


class TestArchivistFinalizeIsSilent(unittest.TestCase):
    """Archivist WorkItems persist their output (audit) but post NO reply
    comment, merge NO ai_context, and flip no triggering comment — their real
    output is the knowledge-card changes done via the shell during dispatch."""

    def _handler(self) -> tuple[WorkItemHandler, mock.MagicMock]:
        api = mock.MagicMock()
        return WorkItemHandler(api=api, config=Config()), api

    def _archivist_item(self) -> WorkItemEntity:
        return WorkItemEntity(
            id="wi-arch", task_id="T-1", target_persona="archivist",
            triggering_comment_id=None,
            prompt_context={"persona_name": "archivist"},
        )

    def test_archivist_output_persisted_but_no_comment(self):
        handler, api = self._handler()
        outcome = DispatchOutcome(
            success=True,
            output={"reply_text": "Created card foo", "context_update": {"k": "v"}},
            metadata={"duration_ms": 10},
        )
        ok = handler._finalize_success(self._archivist_item(), outcome)
        self.assertTrue(ok)
        api.submit_work_item_output.assert_called_once()          # audit kept
        api.create_comment_with_props.assert_not_called()         # silent
        api.update_task.assert_not_called()                       # no ai_context merge
        api.update_comment_props.assert_not_called()              # nothing to flip

    def test_non_archivist_still_posts_comment(self):
        handler, api = self._handler()
        item = WorkItemEntity(
            id="wi-eng", task_id="T-1", target_persona="engineer",
            triggering_comment_id="c-1",
            prompt_context={"persona_name": "engineer"},
        )
        outcome = DispatchOutcome(
            success=True, output={"reply_text": "done"}, metadata={},
        )
        handler._finalize_success(item, outcome)
        api.create_comment_with_props.assert_called_once()


if __name__ == "__main__":
    unittest.main()
