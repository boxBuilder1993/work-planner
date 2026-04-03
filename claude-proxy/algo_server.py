"""Standalone MCP server for algorithm state transition tools.

Run with: uv run --project /path/to/claude-proxy algo_server.py

The ALGO_TASK_ID and ALGO_AI_STATUS env vars must be set per invocation
to bind tools to the correct task.
"""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.server import Server, InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ServerCapabilities

from api_client import ApiClient

server = Server("algo")
api: ApiClient | None = None


def _api() -> ApiClient:
    global api
    if api is None:
        api = ApiClient()
    return api


def _task_id() -> str:
    return os.environ["ALGO_TASK_ID"]


def _ai_status() -> str:
    return os.environ.get("ALGO_AI_STATUS", "")


def _text(text: str) -> list[TextContent]:
    return [TextContent(type="text", text=text)]


# The tool list is dynamic based on ALGO_TOOLS env var
# Proxy sets this to control which tools are available per phase
def _enabled_tools() -> set[str]:
    tools_env = os.environ.get("ALGO_TOOLS", "")
    if not tools_env:
        return set()
    return set(tools_env.split(","))


ALL_TOOLS = {
    "propose_plan": Tool(
        name="propose_plan",
        description="Propose your plan for this task. Posts a PROPOSAL on your task for parent/user to review.",
        inputSchema={"type": "object", "properties": {
            "plan": {"type": "string", "description": "Your proposed plan with deliverables"},
        }, "required": ["plan"]},
    ),
    "request_clarification": Tool(
        name="request_clarification",
        description="Ask parent/user a question. Task pauses until answered.",
        inputSchema={"type": "object", "properties": {
            "question": {"type": "string", "description": "The question to ask"},
        }, "required": ["question"]},
    ),
    "mark_as_planned": Tool(
        name="mark_as_planned",
        description="Call AFTER creating all subtasks. Moves to management mode.",
        inputSchema={"type": "object", "properties": {
            "summary": {"type": "string", "description": "Summary of subtasks created"},
        }, "required": ["summary"]},
    ),
    "mark_as_worker_ready": Tool(
        name="mark_as_worker_ready",
        description="Mark task as simple enough for direct implementation.",
        inputSchema={"type": "object", "properties": {
            "reason": {"type": "string", "description": "Why this is small enough"},
        }, "required": ["reason"]},
    ),
    "propose_work": Tool(
        name="propose_work",
        description="Propose specific actions (PRs, commands, files) before executing.",
        inputSchema={"type": "object", "properties": {
            "plan": {"type": "string", "description": "Specific actions to take"},
        }, "required": ["plan"]},
    ),
    "submit_proof": Tool(
        name="submit_proof",
        description="Submit proof of completion for parent to review.",
        inputSchema={"type": "object", "properties": {
            "proof": {"type": "string", "description": "Evidence: PR links, outputs, results"},
        }, "required": ["proof"]},
    ),
    "submit_summary": Tool(
        name="submit_summary",
        description="Submit completion summary for top-level task (user reviews).",
        inputSchema={"type": "object", "properties": {
            "summary": {"type": "string", "description": "What was accomplished with evidence"},
        }, "required": ["summary"]},
    ),
    "approve_child_proposal": Tool(
        name="approve_child_proposal",
        description="Approve a pending proposal on a child task.",
        inputSchema={"type": "object", "properties": {
            "proposal_id": {"type": "string", "description": "ID of the PROPOSAL to approve"},
        }, "required": ["proposal_id"]},
    ),
    "deny_child_proposal": Tool(
        name="deny_child_proposal",
        description="Deny a pending proposal on a child task with feedback.",
        inputSchema={"type": "object", "properties": {
            "proposal_id": {"type": "string", "description": "ID of the PROPOSAL to deny"},
            "feedback": {"type": "string", "description": "Why denied or what to change"},
        }, "required": ["proposal_id", "feedback"]},
    ),
    "close_subtask": Tool(
        name="close_subtask",
        description="Close a child task after verifying proof.",
        inputSchema={"type": "object", "properties": {
            "subtask_id": {"type": "string", "description": "ID of subtask to close"},
            "feedback": {"type": "string", "description": "Brief feedback"},
        }, "required": ["subtask_id"]},
    ),
    "request_rework": Tool(
        name="request_rework",
        description="Send a child task back for rework.",
        inputSchema={"type": "object", "properties": {
            "subtask_id": {"type": "string", "description": "ID of subtask"},
            "proposal_id": {"type": "string", "description": "ID of proof PROPOSAL to deny"},
            "feedback": {"type": "string", "description": "What to fix"},
        }, "required": ["subtask_id", "proposal_id", "feedback"]},
    ),
    "submit_answer": Tool(
        name="submit_answer",
        description="Submit answer to the task (SimpleAnswer algorithm).",
        inputSchema={"type": "object", "properties": {
            "answer": {"type": "string", "description": "Your answer"},
        }, "required": ["answer"]},
    ),
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    enabled = _enabled_tools()
    if not enabled:
        return list(ALL_TOOLS.values())
    return [t for name, t in ALL_TOOLS.items() if name in enabled]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        client = _api()
        task_id = _task_id()

        if name == "propose_plan":
            client.create_comment(task_id, {
                "text": f"[PLAN PROPOSAL] {arguments['plan']}",
                "commentType": "PROPOSAL",
                "createdBy": task_id,
            })
            client.update_task(task_id, {"props": {"aiStatus": "plan_proposed"}})
            return _text("Plan proposed. Waiting for approval.")

        if name == "request_clarification":
            client.create_comment(task_id, {
                "text": f"[QUESTION] {arguments['question']}",
                "commentType": "PROPOSAL",
                "createdBy": task_id,
            })
            if _ai_status() != "in_progress":
                client.update_task(task_id, {"props": {"aiStatus": "awaiting_input"}})
                return _text("Question posted. Task paused.")
            return _text("Question posted. Continuing management.")

        if name == "mark_as_planned":
            client.create_comment(task_id, {
                "text": f"[PLANNING COMPLETE] {arguments['summary']}",
                "createdBy": task_id,
            })
            client.update_task(task_id, {"props": {"aiStatus": "in_progress"}})
            # Inherit the parent's algorithm so d&dv2 subtasks stay on v2
            parent_task = client.get_task(task_id)
            parent_algo = parent_task.get("props", {}).get("algorithm", "decompose_and_delegate")
            children = client.list_children(task_id)
            for child in children:
                if not child.get("props", {}).get("algorithm"):
                    client.update_task(child["id"], {"props": {
                        "algorithm": parent_algo,
                        "aiStatus": "needs_planning",
                    }})
            return _text(f"Management mode. {len(children)} children initialized.")

        if name == "mark_as_worker_ready":
            client.create_comment(task_id, {
                "text": f"[WORKER READY] {arguments['reason']}",
                "createdBy": task_id,
            })
            client.update_task(task_id, {"props": {"aiStatus": "worker_ready"}})
            return _text("Marked as worker_ready.")

        if name == "propose_work":
            client.create_comment(task_id, {
                "text": f"[WORK PROPOSAL] {arguments['plan']}",
                "commentType": "PROPOSAL",
                "createdBy": task_id,
            })
            client.update_task(task_id, {"props": {"aiStatus": "work_proposed"}})
            return _text("Work proposed. Waiting for approval.")

        if name == "submit_proof":
            client.create_comment(task_id, {
                "text": f"[PROOF OF COMPLETION] {arguments['proof']}",
                "commentType": "PROPOSAL",
                "createdBy": task_id,
            })
            client.update_task(task_id, {"props": {"aiStatus": "proof_submitted"}})
            return _text("Proof submitted. Waiting for parent review.")

        if name == "submit_summary":
            client.create_comment(task_id, {
                "text": f"[COMPLETION SUMMARY] {arguments['summary']}",
                "commentType": "PROPOSAL",
                "createdBy": task_id,
            })
            client.update_task(task_id, {"props": {"aiStatus": "proof_submitted"}})
            return _text("Summary posted. User will review.")

        if name == "approve_child_proposal":
            comment = client.approve_proposal(arguments["proposal_id"])
            child_task = client.get_task(comment["taskId"])
            child_status = child_task.get("props", {}).get("aiStatus", "")
            if child_status == "plan_proposed":
                client.update_task(comment["taskId"], {"props": {"aiStatus": "plan_approved"}})
            elif child_status == "work_proposed":
                client.update_task(comment["taskId"], {"props": {"aiStatus": "work_approved"}})
            elif child_status == "awaiting_input":
                client.update_task(comment["taskId"], {"props": {"aiStatus": "needs_planning"}})
            return _text("Proposal approved and child state updated.")

        if name == "deny_child_proposal":
            comment = client.deny_proposal(arguments["proposal_id"], arguments["feedback"])
            child_task = client.get_task(comment["taskId"])
            child_status = child_task.get("props", {}).get("aiStatus", "")
            if child_status == "plan_proposed":
                client.update_task(comment["taskId"], {"props": {"aiStatus": "needs_planning"}})
            elif child_status == "work_proposed":
                client.update_task(comment["taskId"], {"props": {"aiStatus": "worker_ready"}})
            elif child_status == "awaiting_input":
                client.update_task(comment["taskId"], {"props": {"aiStatus": "needs_planning"}})
            return _text("Proposal denied. Child state reset.")

        if name == "close_subtask":
            if arguments.get("feedback"):
                client.create_comment(arguments["subtask_id"], {
                    "text": f"[REVIEW] {arguments['feedback']}",
                    "createdBy": task_id,
                })
            client.update_task(arguments["subtask_id"], {"status": "CLOSED"})
            return _text(f"Subtask {arguments['subtask_id']} closed.")

        if name == "request_rework":
            client.deny_proposal(arguments["proposal_id"], arguments["feedback"])
            client.update_task(arguments["subtask_id"], {"props": {"aiStatus": "worker_ready"}})
            return _text("Subtask sent back for rework.")

        if name == "submit_answer":
            client.create_comment(task_id, {
                "text": arguments["answer"],
                "createdBy": task_id,
            })
            client.update_task(task_id, {"props": {"aiStatus": "done"}})
            return _text("Answer posted. Done.")

        return _text(f"Unknown tool: {name}")
    except Exception as e:
        return _text(f"Error: {e}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        init_options = InitializationOptions(
            server_name="algo",
            server_version="1.0.0",
            capabilities=ServerCapabilities(tools={}),
        )
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
