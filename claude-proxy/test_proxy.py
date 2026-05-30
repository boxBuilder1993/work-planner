from __future__ import annotations

import json
import os
import sys
import types
import unittest

if "fastapi" not in sys.modules:
    fastapi = types.ModuleType("fastapi")

    class _DummyFastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def post(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        def get(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

    class _DummyHTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    def _dummy_header(default=None, **kwargs):
        return default

    fastapi.FastAPI = _DummyFastAPI
    fastapi.Header = _dummy_header
    fastapi.HTTPException = _DummyHTTPException
    sys.modules["fastapi"] = fastapi

import proxy


class ProxyRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        proxy.runtime_health.clear()

    def test_classify_retryable_quota_failure(self):
        error_type, retryable = proxy._classify_failure("Subscription quota exhausted")
        self.assertEqual(error_type, "quota_exhausted")
        self.assertTrue(retryable)

    def test_resolve_claude_model_maps_old_default_to_cheapest(self):
        self.assertEqual(
            proxy._resolve_claude_model("claude-sonnet-4-6"),
            proxy.CLAUDE_DEFAULT_MODEL,
        )

    def test_resolve_codex_model_maps_claude_request_to_codex_default(self):
        self.assertEqual(
            proxy._resolve_codex_model("claude-sonnet-4-6"),
            proxy.CODEX_DEFAULT_MODEL,
        )

    def test_router_skips_degraded_runtime(self):
        class DummyRuntime:
            def __init__(self, name: str):
                self.name = name

            async def run(self, req):
                raise AssertionError("should not run")

        proxy._degrade_runtime("claude", "rate_limit", "too many requests")
        router = proxy.RuntimeRouter({"claude": DummyRuntime("claude"), "codex": DummyRuntime("codex")})
        req = proxy.RunRequest(prompt="x")
        self.assertEqual([rt.name for rt, _ in router.candidates(req)], ["codex"])

    def test_router_uses_explicit_runtime_recommendations(self):
        class DummyRuntime:
            def __init__(self, name: str):
                self.name = name

            async def run(self, req):
                raise AssertionError("should not run")

        router = proxy.RuntimeRouter({"claude": DummyRuntime("claude"), "codex": DummyRuntime("codex")})
        req = proxy.RunRequest(
            prompt="x",
            model="gpt-5-codex",
            preferred_runtime="codex",
            fallback_runtimes=[{"runtime": "claude", "model": "claude-sonnet-4-6"}],
        )
        candidates = router.candidates(req)
        self.assertEqual([rt.name for rt, _ in candidates], ["codex", "claude"])
        self.assertEqual([candidate_req.model for _, candidate_req in candidates], ["gpt-5-codex", "claude-sonnet-4-6"])


# ─── Chat dispatch additions (workspace derivation + metadata) ────────────
#
# Workspace dir is `WORKSPACE_BASE / task_id`, computed by the proxy. The
# field is intentionally not on RunRequest — pollers don't get a say in
# filesystem layout. Legacy callers with no task_id fall back to REPO_ROOT.


class RunRequestTests(unittest.TestCase):
    def test_run_request_has_no_workspace_path_field(self):
        # Pydantic ignores extras, so old pollers still sending the field
        # don't error — but the field is not part of the model.
        req = proxy.RunRequest(prompt="x")
        self.assertFalse(hasattr(req, "workspace_path"))


class WorkplannerEnvTests(unittest.TestCase):
    def test_omits_workspace_path_when_no_task_id(self):
        req = proxy.RunRequest(prompt="x", workplanner_api_url="http://api", internal_api_key="k")
        env = proxy._workplanner_env(req)
        self.assertNotIn("WORKPLANNER_WORKSPACE_PATH", env)

    def test_includes_workspace_path_derived_from_task_id(self):
        from pathlib import Path
        orig_base = proxy.WORKSPACE_BASE
        proxy.WORKSPACE_BASE = Path("/tmp/wp-test-base")
        try:
            req = proxy.RunRequest(
                prompt="x",
                workplanner_api_url="http://api",
                internal_api_key="k",
                task_id="T-42",
            )
            env = proxy._workplanner_env(req)
            self.assertEqual(env["WORKPLANNER_WORKSPACE_PATH"], "/tmp/wp-test-base/T-42")
            self.assertEqual(env["WORKPLANNER_API_URL"], "http://api")
        finally:
            proxy.WORKSPACE_BASE = orig_base


class StatusResponseTests(unittest.TestCase):
    def test_metadata_defaults_to_empty_dict(self):
        resp = proxy.StatusResponse(status="done")
        self.assertEqual(resp.metadata, {})

    def test_metadata_round_trips(self):
        resp = proxy.StatusResponse(
            status="done",
            result="hi",
            metadata={"duration_ms": 1234, "total_cost_usd": 0.001},
        )
        self.assertEqual(resp.metadata["duration_ms"], 1234)


class RuntimeSuccessTests(unittest.TestCase):
    def test_metadata_defaults_to_empty(self):
        outcome = proxy.RuntimeSuccess(runtime="claude", model="m", result="r")
        self.assertEqual(outcome.metadata, {})

    def test_metadata_independent_per_instance(self):
        a = proxy.RuntimeSuccess(runtime="claude", model="m", result="r")
        b = proxy.RuntimeSuccess(runtime="claude", model="m", result="r")
        a.metadata["x"] = 1
        self.assertNotIn("x", b.metadata)  # field(default_factory=dict), not shared


class ClaudeRuntimeChatDispatchTests(unittest.IsolatedAsyncioTestCase):
    """Mock subprocess + MCP config to verify ClaudeRuntime wiring."""

    def setUp(self) -> None:
        # Record what _run_subprocess was called with so tests can assert.
        self._recorded_cmd: list[str] = []
        self._recorded_cwd = None
        self._mock_stdout = json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 1500,
            "total_cost_usd": 0.0042,
            "stop_reason": "end_turn",
            "result": '{"reply_text": "hi", "context_update": {}}',
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })

        async def fake_run_subprocess(cmd, *, stdin_text="", env=None, cwd=None, timeout=600):
            self._recorded_cmd = list(cmd)
            self._recorded_cwd = cwd
            return 0, self._mock_stdout, ""

        # Patch on the module so ClaudeRuntime.run sees the fake.
        self._orig_run_subprocess = proxy._run_subprocess
        proxy._run_subprocess = fake_run_subprocess

        # Patch _build_claude_mcp_config to a no-op (we're not running real MCP).
        self._orig_build_mcp = proxy._build_claude_mcp_config
        proxy._build_claude_mcp_config = lambda req, path: None

    def tearDown(self) -> None:
        proxy._run_subprocess = self._orig_run_subprocess
        proxy._build_claude_mcp_config = self._orig_build_mcp

    async def test_legacy_path_uses_repo_root_cwd(self):
        req = proxy.RunRequest(prompt="hello", model="claude-haiku-4-5")
        outcome = await proxy.ClaudeRuntime().run(req)
        self.assertIsInstance(outcome, proxy.RuntimeSuccess)
        # No workspace → cwd is REPO_ROOT, no --add-dir flag
        self.assertEqual(self._recorded_cwd, proxy.REPO_ROOT)
        self.assertNotIn("--add-dir", self._recorded_cmd)

    async def test_chat_dispatch_sets_workspace_cwd_and_add_dir(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            orig_base = proxy.WORKSPACE_BASE
            proxy.WORKSPACE_BASE = Path(tmp)
            try:
                req = proxy.RunRequest(
                    prompt="hello",
                    model="claude-haiku-4-5",
                    task_id="T-42",
                )
                outcome = await proxy.ClaudeRuntime().run(req)
                self.assertIsInstance(outcome, proxy.RuntimeSuccess)
                expected_ws = os.path.join(tmp, "T-42")
                # Workspace dir was created
                self.assertTrue(os.path.isdir(expected_ws))
                # cwd set to derived workspace path
                self.assertEqual(str(self._recorded_cwd), expected_ws)
                # --add-dir flag present with workspace path
                self.assertIn("--add-dir", self._recorded_cmd)
                idx = self._recorded_cmd.index("--add-dir")
                self.assertEqual(self._recorded_cmd[idx + 1], expected_ws)
            finally:
                proxy.WORKSPACE_BASE = orig_base

    async def test_metadata_populated_from_claude_json(self):
        req = proxy.RunRequest(prompt="hello", model="claude-haiku-4-5")
        outcome = await proxy.ClaudeRuntime().run(req)
        self.assertIsInstance(outcome, proxy.RuntimeSuccess)
        self.assertEqual(outcome.metadata["duration_ms"], 1500)
        self.assertEqual(outcome.metadata["total_cost_usd"], 0.0042)
        self.assertEqual(outcome.metadata["stop_reason"], "end_turn")
        self.assertIn("usage", outcome.metadata)
        # `result` still extracted as the .result string for backward compat
        self.assertIn("reply_text", outcome.result)

    async def test_metadata_empty_when_output_is_not_json(self):
        async def fake_run_subprocess(cmd, *, stdin_text="", env=None, cwd=None, timeout=600):
            return 0, "not json at all", ""
        proxy._run_subprocess = fake_run_subprocess
        req = proxy.RunRequest(prompt="hello", model="claude-haiku-4-5")
        outcome = await proxy.ClaudeRuntime().run(req)
        self.assertIsInstance(outcome, proxy.RuntimeSuccess)
        self.assertEqual(outcome.metadata, {})
        self.assertEqual(outcome.result, "not json at all")


if __name__ == "__main__":
    unittest.main()
