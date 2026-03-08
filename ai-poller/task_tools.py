"""Read-only MCP tools for the Claude Agent SDK.

Provides four tools that serve task/comment data from in-memory stores,
populated each poll cycle via set_data().
"""

from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from models import TaskEntity, CommentEntity

# In-memory stores populated before each agent run
_tasks: dict[str, TaskEntity] = {}
_comments: list[CommentEntity] = []


def set_data(tasks: list[TaskEntity], comments: list[CommentEntity]) -> None:
    """Populate the in-memory stores with the latest data from Drive."""
    global _tasks, _comments
    _tasks = {t.id: t for t in tasks}
    _comments = comments


def _task_to_dict(t: TaskEntity) -> dict[str, Any]:
    return t.model_dump(by_alias=True)


def _comment_to_dict(c: CommentEntity) -> dict[str, Any]:
    return c.model_dump(by_alias=True)


@tool("get_task", "Get details of a task by its ID", {"task_id": str})
async def get_task(args: dict[str, Any]) -> dict[str, Any]:
    task_id = args["task_id"]
    task = _tasks.get(task_id)
    if task is None:
        return {"content": [{"type": "text", "text": f"Task {task_id} not found."}]}
    return {"content": [{"type": "text", "text": json.dumps(_task_to_dict(task), indent=2)}]}


@tool("get_subtasks", "Get child tasks of a parent task, sorted by createdAt", {"parent_task_id": str})
async def get_subtasks(args: dict[str, Any]) -> dict[str, Any]:
    parent_id = args["parent_task_id"]
    children = [t for t in _tasks.values() if t.parent_id == parent_id]
    children.sort(key=lambda t: t.created_at)
    result = [_task_to_dict(t) for t in children]
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


@tool("get_parent_chain", "Get ancestor chain from root to the given task", {"task_id": str})
async def get_parent_chain(args: dict[str, Any]) -> dict[str, Any]:
    task_id = args["task_id"]
    chain: list[dict[str, Any]] = []
    current = _tasks.get(task_id)
    while current:
        chain.append(_task_to_dict(current))
        current = _tasks.get(current.parent_id) if current.parent_id else None
    chain.reverse()  # root first
    return {"content": [{"type": "text", "text": json.dumps(chain, indent=2)}]}


@tool("get_task_comments", "Get comment thread for a task, sorted chronologically", {"task_id": str})
async def get_task_comments(args: dict[str, Any]) -> dict[str, Any]:
    task_id = args["task_id"]
    thread = [c for c in _comments if c.task_id == task_id]
    thread.sort(key=lambda c: c.created_at)
    result = [_comment_to_dict(c) for c in thread]
    return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}


def create_workplanner_mcp_server():
    """Create an SDK MCP server with all read-only WorkPlanner tools."""
    return create_sdk_mcp_server(
        name="workplanner",
        version="1.0.0",
        tools=[get_task, get_subtasks, get_parent_chain, get_task_comments],
    )
