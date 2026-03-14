"""MCP tools for the Claude Agent SDK.

Provides read and write tools that operate on task/comment data from in-memory
stores, populated each poll cycle via set_data().  Mutation tracking flags let
the processor know when data needs to be uploaded back to Drive.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from collections import deque
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from models import TaskEntity, CommentEntity

# ---------------------------------------------------------------------------
# In-memory stores populated before each agent run
# ---------------------------------------------------------------------------
_tasks: dict[str, TaskEntity] = {}
_comments: list[CommentEntity] = []

# Mutation tracking – reset in set_data() so each agent run starts clean
_tasks_dirty: bool = False
_comments_dirty: bool = False


def set_data(tasks: list[TaskEntity], comments: list[CommentEntity]) -> None:
    """Populate the in-memory stores with the latest data from Drive."""
    global _tasks, _comments, _tasks_dirty, _comments_dirty
    _tasks = {t.id: t for t in tasks}
    _comments = list(comments)
    _tasks_dirty = False
    _comments_dirty = False


def get_dirty_flags() -> tuple[bool, bool]:
    """Return (tasks_dirty, comments_dirty)."""
    return _tasks_dirty, _comments_dirty


def get_current_tasks() -> list[TaskEntity]:
    """Return the current in-memory tasks as a list."""
    return list(_tasks.values())


def get_current_comments() -> list[CommentEntity]:
    """Return the current in-memory comments as a list."""
    return list(_comments)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task_to_dict(t: TaskEntity) -> dict[str, Any]:
    return t.model_dump(by_alias=True)


def _comment_to_dict(c: CommentEntity) -> dict[str, Any]:
    return c.model_dump(by_alias=True)


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------

@tool(
    "create_task",
    "Create a new task. Returns the created task.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Task title"},
            "description": {"type": "string", "description": "Task description"},
            "parent_id": {"type": "string", "description": "Parent task ID (for subtasks)"},
            "priority": {"type": "integer", "description": "Priority (0=none, 1=low, 2=medium, 3=high)"},
            "due_date": {"type": "integer", "description": "Due date as epoch milliseconds"},
            "planned_time": {"type": "integer", "description": "Planned time as epoch milliseconds"},
            "duration": {"type": "number", "description": "Duration in hours"},
        },
        "required": ["title"],
    },
)
async def create_task(args: dict[str, Any]) -> dict[str, Any]:
    global _tasks_dirty
    now = _now_ms()
    task = TaskEntity(
        id=str(uuid.uuid4()),
        parentId=args.get("parent_id"),
        title=args["title"],
        description=args.get("description", ""),
        status="PENDING",
        priority=args.get("priority", 0),
        dueDate=args.get("due_date"),
        plannedTime=args.get("planned_time"),
        duration=args.get("duration"),
        createdAt=now,
        updatedAt=now,
    )
    _tasks[task.id] = task
    _tasks_dirty = True
    return {"content": [{"type": "text", "text": json.dumps(_task_to_dict(task), indent=2)}]}


@tool(
    "update_task",
    "Update fields on an existing task. Only provided fields are changed.",
    {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task to update"},
            "title": {"type": "string", "description": "New title"},
            "description": {"type": "string", "description": "New description"},
            "status": {"type": "string", "description": "New status (PENDING or CLOSED)"},
            "priority": {"type": "integer", "description": "New priority (0-3)"},
            "due_date": {"type": "integer", "description": "New due date as epoch milliseconds"},
            "planned_time": {"type": "integer", "description": "New planned time as epoch milliseconds"},
            "duration": {"type": "number", "description": "New duration in hours"},
        },
        "required": ["task_id"],
    },
)
async def update_task(args: dict[str, Any]) -> dict[str, Any]:
    global _tasks_dirty
    task_id = args["task_id"]
    task = _tasks.get(task_id)
    if task is None:
        return {"content": [{"type": "text", "text": f"Task {task_id} not found."}]}

    if "title" in args:
        task.title = args["title"]
    if "description" in args:
        task.description = args["description"]
    if "status" in args:
        task.status = args["status"]
    if "priority" in args:
        task.priority = args["priority"]
    if "due_date" in args:
        task.due_date = args["due_date"]
    if "planned_time" in args:
        task.planned_time = args["planned_time"]
    if "duration" in args:
        task.duration = args["duration"]

    task.updated_at = _now_ms()
    _tasks_dirty = True
    return {"content": [{"type": "text", "text": json.dumps(_task_to_dict(task), indent=2)}]}


@tool("delete_task", "Delete a task and all its descendants (cascade)", {"task_id": str})
async def delete_task(args: dict[str, Any]) -> dict[str, Any]:
    global _tasks_dirty
    task_id = args["task_id"]
    if task_id not in _tasks:
        return {"content": [{"type": "text", "text": f"Task {task_id} not found."}]}

    # BFS to collect task + all descendants
    to_delete: set[str] = set()
    queue: deque[str] = deque([task_id])
    while queue:
        current_id = queue.popleft()
        if current_id in to_delete:
            continue
        to_delete.add(current_id)
        for t in _tasks.values():
            if t.parent_id == current_id and t.id not in to_delete:
                queue.append(t.id)

    for tid in to_delete:
        _tasks.pop(tid, None)

    _tasks_dirty = True
    return {
        "content": [
            {"type": "text", "text": f"Deleted {len(to_delete)} task(s): {', '.join(sorted(to_delete))}"}
        ]
    }


@tool(
    "add_comment",
    "Add a comment to a task",
    {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task to comment on"},
            "text": {"type": "string", "description": "Comment text"},
        },
        "required": ["task_id", "text"],
    },
)
async def add_comment(args: dict[str, Any]) -> dict[str, Any]:
    global _comments_dirty
    task_id = args["task_id"]
    if task_id not in _tasks:
        return {"content": [{"type": "text", "text": f"Task {task_id} not found."}]}

    now = _now_ms()
    comment = CommentEntity(
        id=str(uuid.uuid4()),
        taskId=task_id,
        text=args["text"],
        createdAt=now,
        updatedAt=now,
    )
    _comments.append(comment)
    _comments_dirty = True
    return {"content": [{"type": "text", "text": json.dumps(_comment_to_dict(comment), indent=2)}]}


# ---------------------------------------------------------------------------
# Shell tools
# ---------------------------------------------------------------------------

@tool(
    "run_command",
    "Run a shell command and return its output. Can run in the background.",
    {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "working_dir": {"type": "string", "description": "Working directory (defaults to home dir)"},
            "timeout": {"type": "number", "description": "Timeout in seconds. Null or omit for no timeout."},
            "background": {"type": "boolean", "description": "If true, run in background and return the PID immediately"},
        },
        "required": ["command"],
    },
)
async def run_command(args: dict[str, Any]) -> dict[str, Any]:
    command = args["command"]
    working_dir = args.get("working_dir")
    timeout = args.get("timeout")
    background = args.get("background", False)

    try:
        if background:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=working_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            result = {"pid": proc.pid, "status": "started in background"}
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

        proc = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        result = {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-10000:] if len(proc.stdout) > 10000 else proc.stdout,
            "stderr": proc.stderr[-5000:] if len(proc.stderr) > 5000 else proc.stderr,
        }
        if len(proc.stdout) > 10000:
            result["stdout_truncated"] = True
        if len(proc.stderr) > 5000:
            result["stderr_truncated"] = True
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": json.dumps({"error": f"Command timed out after {timeout}s"}, indent=2)}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": str(e)}, indent=2)}]}


# ---------------------------------------------------------------------------
# MCP server factory
# ---------------------------------------------------------------------------

def create_workplanner_mcp_server():
    """Create an SDK MCP server with all WorkPlanner tools."""
    return create_sdk_mcp_server(
        name="workplanner",
        version="1.0.0",
        tools=[
            # Read
            get_task, get_subtasks, get_parent_chain, get_task_comments,
            # Write
            create_task, update_task, delete_task, add_comment,
            # Shell
            run_command,
        ],
    )
