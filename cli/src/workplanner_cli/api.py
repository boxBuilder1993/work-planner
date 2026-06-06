"""Thin HTTP client against the backend's /api/internal/* surface.

Intentionally minimal — no model classes, just dicts. The CLI's `render`
module is the only consumer and renders straight from the JSON.
"""

from __future__ import annotations

from typing import Any

import httpx


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str, body: str = ""):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message
        self.body = body


class Client:
    def __init__(self, base_url: str, internal_key: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "X-Internal-Key": internal_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._http.close()

    def _raise(self, r: httpx.Response) -> None:
        if r.is_success:
            return
        try:
            payload = r.json()
            msg = payload.get("error") or payload.get("message") or r.text
        except Exception:
            msg = r.text or r.reason_phrase
        raise ApiError(r.status_code, msg, body=r.text)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        r = self._http.get(path, params=params)
        self._raise(r)
        return r.json()

    def _post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        r = self._http.post(path, json=body or {})
        self._raise(r)
        # Some endpoints (delete-like) return 204 with no body.
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    def _patch(self, path: str, body: dict[str, Any]) -> Any:
        r = self._http.patch(path, json=body)
        self._raise(r)
        return r.json()

    def _delete(self, path: str) -> None:
        r = self._http.delete(path)
        self._raise(r)

    # ── Tasks ────────────────────────────────────────────

    def list_root_tasks(self, status: str | None = None) -> list[dict]:
        params = {"status": status} if status else None
        return self._get("/api/internal/tasks", params=params)

    def search_tasks(
        self,
        query: str | None = None,
        status: str | None = None,
        ai_status: str | None = None,
        algorithm: str | None = None,
        ai_enabled: bool | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if query:
            params["q"] = query
        if status:
            params["status"] = status
        if ai_status:
            params["aiStatus"] = ai_status
        if algorithm:
            params["algorithm"] = algorithm
        if ai_enabled is not None:
            params["aiEnabled"] = "true" if ai_enabled else "false"
        return self._get("/api/internal/tasks/search", params=params)

    def get_task(self, task_id: str) -> dict:
        return self._get(f"/api/internal/tasks/{task_id}")

    def list_children(self, task_id: str) -> list[dict]:
        return self._get(f"/api/internal/tasks/{task_id}/children")

    def create_task(self, body: dict) -> dict:
        return self._post("/api/internal/tasks", body)

    def update_task(self, task_id: str, fields: dict) -> dict:
        return self._patch(f"/api/internal/tasks/{task_id}", fields)

    # Internal API has no DELETE for tasks; user API does. For now the CLI
    # surfaces this as a "soft delete" via status=DELETED if backend supports
    # it, else errors clearly. (The backend currently has no DELETE on the
    # internal mux — see backend/internal/handler/internal.go.)

    # ── Comments ─────────────────────────────────────────

    def list_comments(self, task_id: str) -> list[dict]:
        return self._get(f"/api/internal/tasks/{task_id}/comments")

    def create_comment(
        self,
        task_id: str,
        text: str,
        parent_comment_id: str | None = None,
        comment_type: str = "COMMENT",
        created_by: str = "user",
    ) -> dict:
        body: dict[str, Any] = {
            "text": text,
            "commentType": comment_type,
            "createdBy": created_by,
        }
        if parent_comment_id:
            body["parentCommentId"] = parent_comment_id
        return self._post(f"/api/internal/tasks/{task_id}/comments", body)

    def update_comment(self, comment_id: str, fields: dict) -> dict:
        return self._patch(f"/api/internal/comments/{comment_id}", fields)

    def approve_proposal(self, comment_id: str) -> dict:
        return self._post(f"/api/internal/comments/{comment_id}/approve")

    def deny_proposal(self, comment_id: str, feedback: str = "") -> dict:
        return self._post(
            f"/api/internal/comments/{comment_id}/deny",
            {"feedback": feedback},
        )

    # ── WorkItems ────────────────────────────────────────

    def list_work_items(
        self,
        task_id: str | None = None,
        status: str | None = None,
        persona: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if task_id:
            params["task_id"] = task_id
        if status:
            params["status"] = status
        if persona:
            params["persona"] = persona
        return self._get("/api/internal/work-items", params=params or None)

    def get_work_item(self, work_item_id: str) -> dict:
        return self._get(f"/api/internal/work-items/{work_item_id}")

    def update_work_item(self, work_item_id: str, fields: dict) -> dict:
        return self._patch(f"/api/internal/work-items/{work_item_id}", fields)

    # ── Knowledge Cards ──────────────────────────────────

    def create_knowledge_card(self, card_id: str, content: str, tags: list[str]) -> dict:
        return self._post(
            "/api/internal/knowledge-cards",
            {"id": card_id, "content": content, "tags": tags},
        )

    def get_knowledge_card(self, card_id: str) -> dict:
        return self._get(f"/api/internal/knowledge-cards/{card_id}")

    def list_knowledge_cards(self, tag: str | None = None, include_invalid: bool = False) -> list[dict]:
        params: dict[str, Any] = {}
        if tag:
            params["tag"] = tag
        if include_invalid:
            params["includeInvalid"] = "true"
        return self._get("/api/internal/knowledge-cards", params=params or None)

    def search_knowledge_cards(
        self,
        query: str | None = None,
        tag: str | None = None,
        include_invalid: bool = False,
        limit: int | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if query:
            params["q"] = query
        if tag:
            params["tag"] = tag
        if include_invalid:
            params["includeInvalid"] = "true"
        if limit:
            params["limit"] = str(limit)
        return self._get("/api/internal/knowledge-cards/search", params=params or None)

    def update_knowledge_card(self, card_id: str, fields: dict) -> dict:
        return self._patch(f"/api/internal/knowledge-cards/{card_id}", fields)

    def delete_knowledge_card(self, card_id: str) -> None:
        self._delete(f"/api/internal/knowledge-cards/{card_id}")
