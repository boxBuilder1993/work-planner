from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
