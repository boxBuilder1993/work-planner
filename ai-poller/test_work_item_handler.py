"""Unit tests for work_item_handler — the WorkItem dispatcher.

Covers the pure helpers (proxy response parsing, telemetry shaping). The
HTTP / state-machine wiring is covered by the backend tests and the
manual smoke-test in Phase 1.
"""

from __future__ import annotations

import unittest

from work_item_handler import _parse_proxy_done, _parse_result_str, _telemetry_props


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


if __name__ == "__main__":
    unittest.main()
