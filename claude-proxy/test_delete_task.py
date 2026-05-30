"""Integration test for the delete_task MCP tool.

Requires WORKPLANNER_API_URL and INTERNAL_API_KEY to be set.
Skip automatically when env vars are absent so CI without backend access
doesn't fail.

Run manually:
    WORKPLANNER_API_URL=https://backend-production-e479b.up.railway.app \
    INTERNAL_API_KEY=<key> \
    uv run --project /path/to/claude-proxy python test_delete_task.py
"""

from __future__ import annotations

import os
import unittest

REQUIRED_ENV = ("WORKPLANNER_API_URL", "INTERNAL_API_KEY")
_missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]


@unittest.skipIf(_missing, f"Missing env vars: {_missing} — skipping integration test")
class DeleteTaskIntegrationTest(unittest.TestCase):
    """Create a task, delete it, assert 404 on get."""

    def setUp(self) -> None:
        from api_client import ApiClient
        self.client = ApiClient()

    def test_create_then_delete_then_404(self) -> None:
        # parentId is required by the backend for internal task creation.
        # We use a well-known test parent; the task is deleted before the
        # test exits so it won't pollute any real task tree.
        parent_id = os.environ.get("TEST_PARENT_TASK_ID", "b5403110-5f3f-4f68-ae35-016dd839884b")

        # 1. Create a throwaway task.
        task = self.client.create_task({
            "title": "[test] delete_task integration probe — safe to delete",
            "description": "Created by test_delete_task.py; deleted in the same test run.",
            "parentId": parent_id,
        })
        task_id: str = task["id"]
        self.assertIsNotNone(task_id)

        # 2. Confirm it's fetchable.
        fetched = self.client.get_task(task_id)
        self.assertEqual(fetched["id"], task_id)

        # 3. Delete it.
        self.client.delete_task(task_id)

        # 4. Assert the backend returns 404.
        import requests
        try:
            self.client.get_task(task_id)
            self.fail(f"Expected 404 after delete but get_task succeeded for {task_id!r}")
        except requests.HTTPError as exc:
            self.assertEqual(exc.response.status_code, 404,
                             f"Expected 404, got {exc.response.status_code}")


if __name__ == "__main__":
    unittest.main()
