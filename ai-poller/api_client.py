"""HTTP client for the WorkPlanner backend API."""

from __future__ import annotations

import logging
from typing import Any

import requests

from models import TaskEntity, CommentEntity

logger = logging.getLogger(__name__)


class ApiClient:
    """Thin wrapper around the WorkPlanner REST API."""

    def __init__(self, base_url: str, jwt: str = "", internal_api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self._is_internal = bool(internal_api_key)
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        if internal_api_key:
            self.session.headers["X-Internal-Key"] = internal_api_key
        elif jwt:
            self.session.headers["Authorization"] = f"Bearer {jwt}"

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
        if self._is_internal:
            params: dict[str, str] = {}
            if status:
                params["status"] = status
            return [TaskEntity(**t) for t in self._get("/api/internal/tasks", params or None)]
        params2: dict[str, str] = {"root": "true"}
        if status:
            params2["status"] = status
        return [TaskEntity(**t) for t in self._get("/api/tasks", params2)]

    def get_task(self, task_id: str) -> TaskEntity:
        if self._is_internal:
            return TaskEntity(**self._get(f"/api/internal/tasks/{task_id}"))
        return TaskEntity(**self._get(f"/api/tasks/{task_id}"))

    def list_children(self, task_id: str) -> list[TaskEntity]:
        if self._is_internal:
            return [TaskEntity(**t) for t in self._get(f"/api/internal/tasks/{task_id}/children")]
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
        ai_enabled: bool = False,
        props: dict | None = None,
    ) -> TaskEntity:
        body: dict[str, Any] = {
            "title": title,
            "description": description,
            "priority": priority,
            "aiEnabled": ai_enabled,
        }
        if parent_id is not None:
            body["parentId"] = parent_id
        if due_date is not None:
            body["dueDate"] = due_date
        if planned_time is not None:
            body["plannedTime"] = planned_time
        if duration is not None:
            body["duration"] = duration
        if props is not None:
            body["props"] = props
        if self._is_internal:
            return TaskEntity(**self._post("/api/internal/tasks", body))
        return TaskEntity(**self._post("/api/tasks", body))

    def update_task(self, task_id: str, **fields: Any) -> TaskEntity:
        if self._is_internal:
            return TaskEntity(**self._patch(f"/api/internal/tasks/{task_id}", fields))
        return TaskEntity(**self._patch(f"/api/tasks/{task_id}", fields))

    def delete_task(self, task_id: str) -> None:
        self._delete(f"/api/tasks/{task_id}")

    # ── Comments ───────────────────────────────────────────────────────

    def list_comments(
        self,
        task_id: str,
        comment_type: str | None = None,
    ) -> list[CommentEntity]:
        """List comments for a task, optionally filtered by type (e.g. PROPOSAL)."""
        params: dict[str, str] | None = None
        if comment_type is not None:
            params = {"type": comment_type}
        if self._is_internal:
            return [CommentEntity(**c) for c in self._get(f"/api/internal/tasks/{task_id}/comments", params)]
        return [CommentEntity(**c) for c in self._get(f"/api/tasks/{task_id}/comments", params)]

    def create_comment(
        self,
        task_id: str,
        text: str,
        parent_comment_id: str | None = None,
        comment_type: str = "COMMENT",
        created_by: str = "user",
    ) -> CommentEntity:
        """Create a comment on a task with optional threading and type metadata."""
        body: dict[str, Any] = {
            "text": text,
            "commentType": comment_type,
            "createdBy": created_by,
        }
        if parent_comment_id is not None:
            body["parentCommentId"] = parent_comment_id
        if self._is_internal:
            return CommentEntity(**self._post(f"/api/internal/tasks/{task_id}/comments", body))
        return CommentEntity(**self._post(f"/api/tasks/{task_id}/comments", body))

    def create_comment_with_props(
        self,
        task_id: str,
        text: str,
        parent_comment_id: str | None,
        comment_type: str,
        created_by: str,
        props: dict[str, Any],
    ) -> CommentEntity:
        """Create a comment carrying initial props (chat dispatch uses this for AI replies)."""
        body: dict[str, Any] = {
            "text": text,
            "commentType": comment_type,
            "createdBy": created_by,
            "props": props,
        }
        if parent_comment_id is not None:
            body["parentCommentId"] = parent_comment_id
        if self._is_internal:
            return CommentEntity(**self._post(f"/api/internal/tasks/{task_id}/comments", body))
        return CommentEntity(**self._post(f"/api/tasks/{task_id}/comments", body))

    def update_comment_props(self, comment_id: str, props_patch: dict[str, Any]) -> dict[str, Any]:
        """Partial merge of `props` onto a comment (internal only).

        Top-level keys in `props_patch` overwrite existing keys; arrays are
        replaced wholesale. Mirrors the task.props merge semantics in the backend.
        """
        if not self._is_internal:
            raise RuntimeError("update_comment_props requires INTERNAL_API_KEY (internal endpoint only)")
        return self._patch(f"/api/internal/comments/{comment_id}", {"props": props_patch})

    def list_comments_needing_ai_reply(self) -> list[CommentEntity]:
        """Return comments containing @ai mentions that have not yet been dispatched.

        Filters server-side on text ILIKE '%@ai%' AND props->>'ai-comment-status' IS NULL.
        Internal endpoint only — the chat poller is the sole caller.
        """
        if not self._is_internal:
            raise RuntimeError("list_comments_needing_ai_reply requires INTERNAL_API_KEY")
        params = {"needs_ai_reply": "true"}
        return [CommentEntity(**c) for c in self._get("/api/internal/comments", params)]

    def approve_proposal(self, comment_id: str) -> CommentEntity:
        """Approve a PROPOSAL comment."""
        if self._is_internal:
            return CommentEntity(**self._post(f"/api/internal/comments/{comment_id}/approve"))
        return CommentEntity(**self._post(f"/api/comments/{comment_id}/approve"))

    def deny_proposal(self, comment_id: str, feedback: str = "") -> CommentEntity:
        """Deny a PROPOSAL comment with optional feedback."""
        if self._is_internal:
            return CommentEntity(**self._post(f"/api/internal/comments/{comment_id}/deny", {"feedback": feedback}))
        return CommentEntity(**self._post(f"/api/comments/{comment_id}/deny", {"feedback": feedback}))

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
