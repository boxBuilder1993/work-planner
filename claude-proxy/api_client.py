"""Thin API client for the WorkPlanner backend.

Used by MCP servers to call the backend from the proxy machine.
"""

from __future__ import annotations

import os
from typing import Any

import requests


class ApiClient:
    def __init__(self) -> None:
        self.base_url = os.environ["WORKPLANNER_API_URL"].rstrip("/")
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        key = os.environ.get("INTERNAL_API_KEY", "")
        if key:
            self.session.headers["X-Internal-Key"] = key

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _get(self, path: str, params: dict | None = None) -> Any:
        r = self.session.get(self._url(path), params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict | None = None) -> Any:
        r = self.session.post(self._url(path), json=body or {})
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict) -> Any:
        r = self.session.patch(self._url(path), json=body)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> None:
        r = self.session.delete(self._url(path))
        r.raise_for_status()

    # Tasks
    def get_task(self, task_id: str) -> dict:
        return self._get(f"/api/internal/tasks/{task_id}")

    def list_children(self, task_id: str) -> list[dict]:
        return self._get(f"/api/internal/tasks/{task_id}/children")

    def search_tasks(self, status: str | None = None, ai_status: str | None = None,
                     algorithm: str | None = None, ai_enabled: bool | None = None) -> list[dict]:
        params: dict[str, str] = {}
        if status:
            params["status"] = status
        if ai_status:
            params["aiStatus"] = ai_status
        if algorithm:
            params["algorithm"] = algorithm
        if ai_enabled is not None:
            params["aiEnabled"] = str(ai_enabled).lower()
        return self._get("/api/internal/tasks/search", params or None)

    def create_task(self, body: dict) -> dict:
        return self._post("/api/internal/tasks", body)

    def update_task(self, task_id: str, body: dict) -> dict:
        return self._patch(f"/api/internal/tasks/{task_id}", body)

    def delete_task(self, task_id: str) -> None:
        self._delete(f"/api/internal/tasks/{task_id}")

    def get_breadcrumbs(self, task_id: str) -> list[dict]:
        return self._get(f"/api/tasks/{task_id}/breadcrumbs")

    # Comments
    def list_comments(self, task_id: str, comment_type: str | None = None) -> list[dict]:
        params = {"type": comment_type} if comment_type else None
        return self._get(f"/api/internal/tasks/{task_id}/comments", params)

    def create_comment(self, task_id: str, body: dict) -> dict:
        return self._post(f"/api/internal/tasks/{task_id}/comments", body)

    def approve_proposal(self, comment_id: str) -> dict:
        return self._post(f"/api/internal/comments/{comment_id}/approve")

    def deny_proposal(self, comment_id: str, feedback: str = "") -> dict:
        return self._post(f"/api/internal/comments/{comment_id}/deny", {"feedback": feedback})

    # WorkItems — used by the MCP get_work_item / list_work_items tools.
    def get_work_item(self, work_item_id: str) -> dict:
        return self._get(f"/api/internal/work-items/{work_item_id}")

    def list_work_items(
        self,
        task_id: str | None = None,
        status: str | None = None,
        persona: str | None = None,
    ) -> list[dict]:
        params: dict[str, str] = {}
        if task_id:
            params["task_id"] = task_id
        if status:
            params["status"] = status
        if persona:
            params["persona"] = persona
        return self._get("/api/internal/work-items", params or None)
