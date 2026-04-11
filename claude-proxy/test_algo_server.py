from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest

if "mcp.server" not in sys.modules:
    mcp_server = types.ModuleType("mcp.server")

    class _DummyServer:
        def __init__(self, *args, **kwargs):
            pass

        def list_tools(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        def call_tool(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

    class _DummyInitializationOptions:
        def __init__(self, *args, **kwargs):
            pass

    mcp_server.Server = _DummyServer
    mcp_server.InitializationOptions = _DummyInitializationOptions
    sys.modules["mcp.server"] = mcp_server

if "mcp.server.stdio" not in sys.modules:
    mcp_stdio = types.ModuleType("mcp.server.stdio")

    async def _dummy_stdio_server():
        raise AssertionError("not used in tests")

    mcp_stdio.stdio_server = _dummy_stdio_server
    sys.modules["mcp.server.stdio"] = mcp_stdio

if "mcp.types" not in sys.modules:
    mcp_types = types.ModuleType("mcp.types")

    class _DummyTool:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _DummyTextContent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _DummyServerCapabilities:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    mcp_types.Tool = _DummyTool
    mcp_types.TextContent = _DummyTextContent
    mcp_types.ServerCapabilities = _DummyServerCapabilities
    sys.modules["mcp.types"] = mcp_types

import algo_server


class _DummyClient:
    def __init__(self, comments: list[dict] | None = None):
        self.comments = comments or []
        self.created_comments: list[dict] = []
        self.updated_tasks: list[tuple[str, dict]] = []

    def list_comments(self, task_id: str, comment_type: str | None = None) -> list[dict]:
        return list(self.comments)

    def create_comment(self, task_id: str, body: dict) -> dict:
        self.created_comments.append(body)
        return body

    def update_task(self, task_id: str, body: dict) -> dict:
        self.updated_tasks.append((task_id, body))
        return body


class AlgoServerIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["ALGO_TASK_ID"] = "task-123"
        os.environ["ALGO_AI_STATUS"] = "propose"
        algo_server.api = None

    def test_propose_plan_reuses_identical_pending_proposal(self):
        algo_server.api = _DummyClient(comments=[{
            "commentType": "PROPOSAL",
            "proposalStatus": "PENDING",
            "createdBy": "task-123",
            "text": "[PLAN PROPOSAL] inspect web first",
        }])

        result = asyncio.run(algo_server.call_tool("propose_plan", {"plan": "inspect web first"}))

        self.assertEqual(result[0].text, "Existing pending plan already posted. Waiting for approval.")
        self.assertEqual(algo_server.api.created_comments, [])
        self.assertEqual(algo_server.api.updated_tasks, [])

    def test_request_clarification_reuses_identical_pending_question(self):
        algo_server.api = _DummyClient(comments=[{
            "commentType": "PROPOSAL",
            "proposalStatus": "PENDING",
            "createdBy": "task-123",
            "text": "[QUESTION] should I inspect the repo root?",
        }])

        result = asyncio.run(algo_server.call_tool("request_clarification", {"question": "should I inspect the repo root?"}))

        self.assertEqual(result[0].text, "Existing pending question already posted. Waiting for input.")
        self.assertEqual(algo_server.api.created_comments, [])
        self.assertEqual(algo_server.api.updated_tasks, [])

    def test_request_clarification_clamps_awaiting_input_resume_state(self):
        os.environ["ALGO_AI_STATUS"] = "awaiting_input"
        algo_server.api = _DummyClient()

        result = asyncio.run(algo_server.call_tool("request_clarification", {"question": "next?"}))

        self.assertEqual(result[0].text, "Question posted. Task paused.")
        self.assertEqual(
            algo_server.api.updated_tasks,
            [("task-123", {"props": {"aiStatus": "awaiting_input", "resumeState": "propose"}})],
        )


if __name__ == "__main__":
    unittest.main()
