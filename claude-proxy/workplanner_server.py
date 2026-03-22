"""Standalone MCP server for WorkPlanner task/comment tools.

Run with: uv run --project /path/to/claude-proxy workplanner_server.py
Communicates over stdio (JSON-RPC).
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from api_client import ApiClient

server = Server("workplanner")
api: ApiClient | None = None


def _api() -> ApiClient:
    global api
    if api is None:
        api = ApiClient()
    return api


def _text(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=text)]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="get_task", description="Get task details by ID",
             inputSchema={"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}),
        Tool(name="get_subtasks", description="Get child tasks",
             inputSchema={"type": "object", "properties": {"parent_task_id": {"type": "string"}}, "required": ["parent_task_id"]}),
        Tool(name="get_parent_chain", description="Get ancestor chain from root to task",
             inputSchema={"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}),
        Tool(name="get_task_comments", description="Get comments for a task",
             inputSchema={"type": "object", "properties": {
                 "task_id": {"type": "string"},
                 "comment_type": {"type": "string", "description": "Filter: COMMENT or PROPOSAL"},
             }, "required": ["task_id"]}),
        Tool(name="create_task", description="Create a new task",
             inputSchema={"type": "object", "properties": {
                 "title": {"type": "string"},
                 "description": {"type": "string"},
                 "parentId": {"type": "string"},
                 "priority": {"type": "integer"},
                 "aiEnabled": {"type": "boolean"},
                 "props": {"type": "object"},
             }, "required": ["title"]}),
        Tool(name="update_task", description="Update task fields",
             inputSchema={"type": "object", "properties": {
                 "task_id": {"type": "string"},
                 "title": {"type": "string"},
                 "description": {"type": "string"},
                 "status": {"type": "string"},
                 "priority": {"type": "integer"},
                 "props": {"type": "object"},
             }, "required": ["task_id"]}),
        Tool(name="delete_task", description="Delete a task",
             inputSchema={"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}),
        Tool(name="add_comment", description="Add a comment to a task",
             inputSchema={"type": "object", "properties": {
                 "task_id": {"type": "string"},
                 "text": {"type": "string"},
                 "parent_comment_id": {"type": "string"},
                 "comment_type": {"type": "string", "description": "COMMENT or PROPOSAL"},
                 "created_by": {"type": "string"},
             }, "required": ["task_id", "text"]}),
        Tool(name="run_command", description="Run a shell command",
             inputSchema={"type": "object", "properties": {
                 "command": {"type": "string"},
                 "working_dir": {"type": "string"},
                 "timeout": {"type": "number"},
             }, "required": ["command"]}),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        client = _api()

        if name == "get_task":
            return _text(json.dumps(client.get_task(arguments["task_id"]), indent=2))

        if name == "get_subtasks":
            return _text(json.dumps(client.list_children(arguments["parent_task_id"]), indent=2))

        if name == "get_parent_chain":
            return _text(json.dumps(client.get_breadcrumbs(arguments["task_id"]), indent=2))

        if name == "get_task_comments":
            return _text(json.dumps(
                client.list_comments(arguments["task_id"], arguments.get("comment_type")),
                indent=2,
            ))

        if name == "create_task":
            body = {k: v for k, v in arguments.items() if v is not None}
            return _text(json.dumps(client.create_task(body), indent=2))

        if name == "update_task":
            task_id = arguments.pop("task_id")
            body = {k: v for k, v in arguments.items() if v is not None}
            return _text(json.dumps(client.update_task(task_id, body), indent=2))

        if name == "delete_task":
            client.delete_task(arguments["task_id"])
            return _text(f"Deleted task {arguments['task_id']}")

        if name == "add_comment":
            body: dict[str, Any] = {
                "text": arguments["text"],
                "commentType": arguments.get("comment_type", "COMMENT"),
                "createdBy": arguments.get("created_by", "user"),
            }
            if arguments.get("parent_comment_id"):
                body["parentCommentId"] = arguments["parent_comment_id"]
            return _text(json.dumps(client.create_comment(arguments["task_id"], body), indent=2))

        if name == "run_command":
            proc = subprocess.run(
                arguments["command"],
                shell=True,
                cwd=arguments.get("working_dir"),
                capture_output=True,
                text=True,
                timeout=arguments.get("timeout", 120),
            )
            result = {
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-10000:] if len(proc.stdout) > 10000 else proc.stdout,
                "stderr": proc.stderr[-5000:] if len(proc.stderr) > 5000 else proc.stderr,
            }
            return _text(json.dumps(result, indent=2))

        return _text(f"Unknown tool: {name}")
    except Exception as e:
        return _text(f"Error: {e}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
