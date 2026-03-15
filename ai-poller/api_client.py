"""HTTP client for the WorkPlanner backend API."""

from __future__ import annotations

import logging
from typing import Any

import requests

from models import TaskEntity, CommentEntity

logger = logging.getLogger(__name__)


class ApiClient:
    """Thin wrapper around the WorkPlanner REST API."""

    def __init__(self, base_url: str, jwt: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {jwt}"
        self.session.headers["Content-Type"] = "application/json"

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        r = self.session.get(self._url(path), params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        r = self.session.post(self._url(path), json=body)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict[str, Any] | None = None) -> Any:
        r = self.session.patch(self._url(path), json=body)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> None:
        r = self.session.delete(self._url(path))
        r.raise_for_status()

    # ── Tasks ──────────────────────────────────────────────────────────

    def list_root_tasks(self, status: str | None = None) -> list[TaskEntity]:
        params: dict[str, str] = {"root": "true"}
        if status:
            params["status"] = status
        return [TaskEntity(**t) for t in self._get("/api/tasks", params)]

    def get_task(self, task_id: str) -> TaskEntity:
        return TaskEntity(**self._get(f"/api/tasks/{task_id}"))

    def list_children(self, task_id: str) -> list[TaskEntity]:
        return [TaskEntity(**t) for t in self._get(f"/api/tasks/{task_id}/children")]

    def get_breadcrumbs(self, task_id: str) -> list[TaskEntity]:
        return [TaskEntity(**t) for t in self._get(f"/api/tasks/{task_id}/breadcrumbs")]

    def create_task(
        self,
        title: str,
        description: str = "",
        parent_id: str | None = None,
        priority: int = 0,
        due_date: int | None = None,
        planned_time: int | None = None,
        duration: float | None = None,
    ) -> TaskEntity:
        body: dict[str, Any] = {"title": title, "description": description, "priority": priority}
        if parent_id is not None:
            body["parent_id"] = parent_id
        if due_date is not None:
            body["due_date"] = due_date
        if planned_time is not None:
            body["planned_time"] = planned_time
        if duration is not None:
            body["duration"] = duration
        return TaskEntity(**self._post("/api/tasks", body))

    def update_task(self, task_id: str, **fields: Any) -> TaskEntity:
        return TaskEntity(**self._patch(f"/api/tasks/{task_id}", fields))

    def delete_task(self, task_id: str) -> None:
        self._delete(f"/api/tasks/{task_id}")

    # ── Comments ───────────────────────────────────────────────────────

    def list_comments(self, task_id: str) -> list[CommentEntity]:
        return [CommentEntity(**c) for c in self._get(f"/api/tasks/{task_id}/comments")]

    def create_comment(self, task_id: str, text: str) -> CommentEntity:
        return CommentEntity(**self._post(f"/api/tasks/{task_id}/comments", {"text": text}))

    def delete_comment(self, comment_id: str) -> None:
        self._delete(f"/api/comments/{comment_id}")

    # ── Helpers ────────────────────────────────────────────────────────

    def get_all_tasks(self) -> list[TaskEntity]:
        """Recursively walk the task tree to collect all tasks."""
        all_tasks: list[TaskEntity] = []
        stack = list(self.list_root_tasks())
        while stack:
            task = stack.pop()
            all_tasks.append(task)
            children = self.list_children(task.id)
            stack.extend(children)
        return all_tasks

    def get_all_comments(self, task_ids: list[str]) -> list[CommentEntity]:
        """Fetch comments for a list of tasks."""
        all_comments: list[CommentEntity] = []
        for tid in task_ids:
            all_comments.extend(self.list_comments(tid))
        return all_comments
