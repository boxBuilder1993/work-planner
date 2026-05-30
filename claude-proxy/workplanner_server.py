"""Standalone MCP server for WorkPlanner task/comment + knowledge tools.

Run with: uv run --project /path/to/claude-proxy workplanner_server.py
Communicates over stdio (JSON-RPC).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

import chromadb
from mcp.server import Server, InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ServerCapabilities

from api_client import ApiClient

server = Server("workplanner")
api: ApiClient | None = None
_chroma_collection = None

# Workspace confinement for `run_command`. Set by claude-proxy when dispatching
# a chat persona; absent when the legacy algorithm path invokes the MCP.
WORKSPACE_PATH = os.environ.get("WORKPLANNER_WORKSPACE_PATH", "")

# Identifies the WorkItem this MCP subprocess is serving. Set by claude-proxy
# when dispatching from the work_item_handler. Lets `get_my_work_item()`
# return the AI's own assignment without needing the AI to know its own id.
MY_WORK_ITEM_ID = os.environ.get("WORK_ITEM_ID", "")


def _api() -> ApiClient:
    global api
    if api is None:
        api = ApiClient()
    return api


def _resolve_working_dir(requested: str | None) -> tuple[str | None, str | None]:
    """Resolve and validate a `run_command` working_dir against WORKSPACE_PATH.

    Returns (resolved_path, error_message). If error_message is not None the
    caller should reject the tool call with that message.

    - If WORKSPACE_PATH is unset (legacy algorithm path), returns requested
      as-is with no constraint.
    - If requested is empty/None, defaults to WORKSPACE_PATH.
    - Relative paths resolve against WORKSPACE_PATH.
    - Absolute paths must lie inside WORKSPACE_PATH (symlink-safe via realpath).
    """
    if not WORKSPACE_PATH:
        return requested, None

    workspace_real = os.path.realpath(WORKSPACE_PATH)

    if not requested:
        return WORKSPACE_PATH, None

    target = requested
    if not os.path.isabs(target):
        target = os.path.join(WORKSPACE_PATH, target)

    target_real = os.path.realpath(target)

    try:
        common = os.path.commonpath([workspace_real, target_real])
    except ValueError:
        return None, (
            f"working_dir must be inside the task workspace ({WORKSPACE_PATH}); "
            f"got '{requested}'"
        )

    if common != workspace_real:
        return None, (
            f"working_dir must be inside the task workspace ({WORKSPACE_PATH}); "
            f"got '{requested}' (resolved to '{target_real}')"
        )

    return target_real, None


def _knowledge():
    global _chroma_collection
    if _chroma_collection is None:
        host = os.environ.get("CHROMADB_HOST", "chromadb-production-8d02.up.railway.app")
        port = int(os.environ.get("CHROMADB_PORT", "443"))
        ssl = port == 443
        client = chromadb.HttpClient(host=host, port=port, ssl=ssl)
        user_id = os.environ.get("CHROMADB_USER_ID", "default")
        collection_name = f"workplanner_knowledge_{user_id.replace('-', '_')}"
        _chroma_collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
    return _chroma_collection


def _text(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=text)]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="get_task", description="Get task details by ID",
             inputSchema={"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}),
        Tool(name="get_subtasks", description="Get child tasks",
             inputSchema={"type": "object", "properties": {"parent_task_id": {"type": "string"}}, "required": ["parent_task_id"]}),
        Tool(name="search_tasks",
             description="Search all tasks with filters. Find tasks by status, AI status, algorithm, or aiEnabled flag.",
             inputSchema={"type": "object", "properties": {
                 "status": {"type": "string", "description": "Filter by task status: PENDING or CLOSED"},
                 "ai_status": {"type": "string", "description": "Filter by AI status: planning, managing, working, etc."},
                 "algorithm": {"type": "string", "description": "Filter by algorithm: simple_answer, decompose_and_delegate, decompose_and_delegate_v2, company_v1"},
                 "ai_enabled": {"type": "boolean", "description": "Filter by aiEnabled flag"},
             }}),
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
        Tool(name="query_knowledge",
             description="Search the company knowledge base. Use this to find past decisions, "
                         "architecture patterns, implementation notes, specs, and lessons learned "
                         "across all projects. Call this anytime you need context — before proposing, "
                         "when stuck, during review, or when making decisions.",
             inputSchema={"type": "object", "properties": {
                 "query": {"type": "string", "description": "Natural language search query"},
                 "limit": {"type": "integer", "description": "Max results (default 5)"},
             }, "required": ["query"]}),
        Tool(name="store_knowledge",
             description="Save knowledge to the company knowledge base for future reference. "
                         "Store specs, architecture decisions, implementation notes, review feedback, "
                         "patterns discovered, and lessons learned.",
             inputSchema={"type": "object", "properties": {
                 "content": {"type": "string", "description": "The knowledge to store"},
                 "work_type": {"type": "string", "description": "Category: requirements_spec, adr, plan, implementation_note, review_feedback, delivery_report, clarification, debug_note"},
                 "tags": {"type": "array", "items": {"type": "string"}, "description": "Free-form tags for context (e.g. project name, tech, feature)"},
             }, "required": ["content", "work_type"]}),
        Tool(name="get_my_work_item",
             description="Return the WorkItem this dispatch is currently executing. "
                         "Includes the assignment (prompt_context), retry count, attempt history, "
                         "and any prior output. Useful when you want to re-read your own "
                         "instructions without scrolling the prompt.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="get_work_item",
             description="Fetch a specific WorkItem by id. Use this to inspect a sibling's "
                         "WorkItem (its assignment + output) without rebuilding context from "
                         "comments.",
             inputSchema={"type": "object", "properties": {
                 "work_item_id": {"type": "string"},
             }, "required": ["work_item_id"]}),
        Tool(name="list_work_items",
             description="List WorkItems, optionally filtered by task, status, or persona. "
                         "Defaults to all WorkItems on the current task when no filter is given. "
                         "Use this to see what siblings have done before you start.",
             inputSchema={"type": "object", "properties": {
                 "task_id": {"type": "string", "description": "Filter by task. Omit to use the current dispatch's task."},
                 "status": {"type": "string", "description": "pending | dispatched | completed | failed | cancelled"},
                 "persona": {"type": "string", "description": "engineer | planner | manager | reviewer | default"},
             }}),
        Tool(name="delete_task",
             description="Permanently delete a task and all its children. "
                         "Irreversible — use only for cleanup of duplicate or probe tasks. "
                         "Requires confirm=True to prevent accidental deletion.",
             inputSchema={"type": "object", "properties": {
                 "task_id": {"type": "string", "description": "ID of the task to delete."},
                 "confirm": {"type": "boolean", "description": "Must be true. Guards against accidental calls."},
             }, "required": ["task_id", "confirm"]}),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        client = _api()

        if name == "get_task":
            return _text(json.dumps(client.get_task(arguments["task_id"]), indent=2))

        if name == "get_subtasks":
            return _text(json.dumps(client.list_children(arguments["parent_task_id"]), indent=2))

        if name == "search_tasks":
            results = client.search_tasks(
                status=arguments.get("status"),
                ai_status=arguments.get("ai_status"),
                algorithm=arguments.get("algorithm"),
                ai_enabled=arguments.get("ai_enabled"),
            )
            return _text(json.dumps(results, indent=2))

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
            resolved_cwd, err = _resolve_working_dir(arguments.get("working_dir"))
            if err:
                return _text(f"Error: {err}")

            proc = subprocess.run(
                arguments["command"],
                shell=True,
                cwd=resolved_cwd,
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

        if name == "query_knowledge":
            collection = _knowledge()
            limit = arguments.get("limit", 5)
            results = collection.query(
                query_texts=[arguments["query"]],
                n_results=limit,
            )
            docs = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    docs.append({
                        "content": results["documents"][0][i] if results["documents"] else "",
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "relevance": 1 - (results["distances"][0][i] if results["distances"] else 1),
                    })
            if not docs:
                return _text("No relevant knowledge found.")
            return _text(json.dumps(docs, indent=2))

        if name == "store_knowledge":
            collection = _knowledge()
            task_id = os.environ.get("ALGO_TASK_ID", "unknown")
            doc_id = f"{task_id}:{arguments['work_type']}:{int(time.time() * 1000)}"
            metadata: dict[str, Any] = {
                "task_id": task_id,
                "work_type": arguments["work_type"],
                "timestamp": int(time.time() * 1000),
            }
            if arguments.get("tags"):
                metadata["tags"] = ",".join(arguments["tags"])
            collection.add(
                ids=[doc_id],
                documents=[arguments["content"]],
                metadatas=[metadata],
            )
            return _text(f"Knowledge stored (id: {doc_id})")

        if name == "get_my_work_item":
            if not MY_WORK_ITEM_ID:
                return _text(
                    "Error: WORK_ITEM_ID env not set on this dispatch — "
                    "this MCP subprocess wasn't spawned by the WorkItem pipeline. "
                    "Use get_work_item(work_item_id=...) instead."
                )
            return _text(json.dumps(client.get_work_item(MY_WORK_ITEM_ID), indent=2))

        if name == "get_work_item":
            return _text(json.dumps(client.get_work_item(arguments["work_item_id"]), indent=2))

        if name == "list_work_items":
            # Default to the current dispatch's task scope if no task_id is
            # given — most natural use is "what have my siblings done?".
            task_id = arguments.get("task_id")
            if not task_id and MY_WORK_ITEM_ID:
                try:
                    me = client.get_work_item(MY_WORK_ITEM_ID)
                    task_id = me.get("taskId")
                except Exception:
                    pass
            results = client.list_work_items(
                task_id=task_id,
                status=arguments.get("status"),
                persona=arguments.get("persona"),
            )
            return _text(json.dumps(results, indent=2))

        if name == "delete_task":
            if not arguments.get("confirm"):
                return _text(
                    "Error: delete_task requires confirm=True. "
                    "This is a permanent, irreversible operation. "
                    "Pass confirm=True only when you are certain the task should be deleted."
                )
            task_id = arguments["task_id"]
            client.delete_task(task_id)
            return _text(json.dumps({"ok": True, "id": task_id}))

        return _text(f"Unknown tool: {name}")
    except Exception as e:
        return _text(f"Error: {e}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = InitializationOptions(
            server_name="workplanner",
            server_version="1.0.0",
            capabilities=ServerCapabilities(tools={}),
        )
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
