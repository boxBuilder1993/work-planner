"""MCP tools for the Claude Agent SDK.

Tools call the WorkPlanner backend API directly via a shared ApiClient instance.
Set the client before each agent run via set_api_client().
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from api_client import ApiClient

# ---------------------------------------------------------------------------
# Shared API client — set before each agent run
# ---------------------------------------------------------------------------
_api: ApiClient | None = None


def set_api_client(client: ApiClient) -> None:
    """Set the API client used by all MCP tools."""
    global _api
    _api = client


def _client() -> ApiClient:
    if _api is None:
        raise RuntimeError("API client not set — call set_api_client() first")
    return _api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task_json(task) -> str:
    return json.dumps(task.model_dump(), indent=2)


def _comment_json(comment) -> str:
    return json.dumps(comment.model_dump(), indent=2)


def _result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

@tool("get_task", "Get details of a task by its ID", {"task_id": str})
async def get_task(args: dict[str, Any]) -> dict[str, Any]:
    try:
        task = _client().get_task(args["task_id"])
        return _result(_task_json(task))
    except Exception as e:
        return _result(f"Error: {e}")


@tool("get_subtasks", "Get child tasks of a parent task, sorted by createdAt", {"parent_task_id": str})
async def get_subtasks(args: dict[str, Any]) -> dict[str, Any]:
    try:
        children = _client().list_children(args["parent_task_id"])
        return _result(json.dumps([t.model_dump() for t in children], indent=2))
    except Exception as e:
        return _result(f"Error: {e}")


@tool("get_parent_chain", "Get ancestor chain from root to the given task", {"task_id": str})
async def get_parent_chain(args: dict[str, Any]) -> dict[str, Any]:
    try:
        crumbs = _client().get_breadcrumbs(args["task_id"])
        return _result(json.dumps([t.model_dump() for t in crumbs], indent=2))
    except Exception as e:
        return _result(f"Error: {e}")


@tool("get_task_comments", "Get comment thread for a task, sorted chronologically", {"task_id": str})
async def get_task_comments(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comments = _client().list_comments(args["task_id"])
        return _result(json.dumps([c.model_dump() for c in comments], indent=2))
    except Exception as e:
        return _result(f"Error: {e}")


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
    try:
        task = _client().create_task(
            title=args["title"],
            description=args.get("description", ""),
            parent_id=args.get("parent_id"),
            priority=args.get("priority", 0),
            due_date=args.get("due_date"),
            planned_time=args.get("planned_time"),
            duration=args.get("duration"),
        )
        return _result(_task_json(task))
    except Exception as e:
        return _result(f"Error creating task: {e}")


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
    try:
        task_id = args.pop("task_id")
        task = _client().update_task(task_id, **args)
        return _result(_task_json(task))
    except Exception as e:
        return _result(f"Error updating task: {e}")


@tool("delete_task", "Delete a task and all its descendants (cascade)", {"task_id": str})
async def delete_task(args: dict[str, Any]) -> dict[str, Any]:
    try:
        _client().delete_task(args["task_id"])
        return _result(f"Deleted task {args['task_id']}")
    except Exception as e:
        return _result(f"Error deleting task: {e}")


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
    try:
        comment = _client().create_comment(args["task_id"], args["text"])
        return _result(_comment_json(comment))
    except Exception as e:
        return _result(f"Error adding comment: {e}")


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
            return _result(json.dumps({"pid": proc.pid, "status": "started in background"}, indent=2))

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
        return _result(json.dumps(result, indent=2))

    except subprocess.TimeoutExpired:
        return _result(json.dumps({"error": f"Command timed out after {timeout}s"}, indent=2))
    except Exception as e:
        return _result(json.dumps({"error": str(e)}, indent=2))


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
