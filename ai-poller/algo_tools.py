"""Algorithm-specific MCP tools for state transitions.

Each algorithm gets its own MCP server with tools that let the agent
explicitly drive the state machine. This replaces implicit on_complete
inspection with explicit agent decisions.
"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from api_client import ApiClient


# ---------------------------------------------------------------------------
# Shared state — set before each agent run by the spawner
# ---------------------------------------------------------------------------

_api: ApiClient | None = None
_task_id: str = ""


def set_algo_context(api: ApiClient, task_id: str) -> None:
    """Set the API client and task ID for algorithm tools."""
    global _api, _task_id
    _api = api
    _task_id = task_id


def _client() -> ApiClient:
    if _api is None:
        raise RuntimeError("Algo context not set — call set_algo_context() first")
    return _api


def _result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


# ---------------------------------------------------------------------------
# DecomposeAndDelegate tools
# ---------------------------------------------------------------------------

@tool(
    "mark_as_planned",
    "Call this AFTER you have created subtasks. Signals that decomposition is complete "
    "and moves the task to management mode. Each child task will be picked up by its own agent.",
    {
        "type": "object",
        "properties": {},
    },
)
async def mark_as_planned(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        task_id = _task_id

        # Set own status to in_progress
        api.update_task(task_id, props={"aiStatus": "in_progress"})

        # Initialize children with D&D algorithm
        children = api.list_children(task_id)
        initialized = 0
        for child in children:
            if not child.props.get("algorithm"):
                api.update_task(child.id, props={
                    "algorithm": "decompose_and_delegate",
                    "aiStatus": "needs_planning",
                })
                initialized += 1

        return _result(
            f"Task moved to in_progress. {initialized} child task(s) initialized for planning."
        )
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "mark_as_worker_ready",
    "Call this when you determine the task is simple enough to implement directly "
    "without subtasks. The next agent run will be in implementation mode with full code tools.",
    {
        "type": "object",
        "properties": {},
    },
)
async def mark_as_worker_ready(args: dict[str, Any]) -> dict[str, Any]:
    try:
        _client().update_task(_task_id, props={"aiStatus": "worker_ready"})
        return _result("Task marked as worker_ready. Next run will be in implementation mode.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "request_clarification",
    "Ask the user or parent manager a question before proceeding. "
    "The task will pause until they reply.",
    {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask",
            },
        },
        "required": ["question"],
    },
)
async def request_clarification(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        api.create_comment(
            task_id=_task_id,
            text=args["question"],
            created_by=_task_id,
        )
        api.update_task(_task_id, props={"aiStatus": "awaiting_input"})
        return _result("Question posted. Task paused until a reply is received.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "submit_proof",
    "Submit proof of completion to your parent task. Include concrete evidence: "
    "command outputs, test results, PR links, file changes.",
    {
        "type": "object",
        "properties": {
            "parent_task_id": {
                "type": "string",
                "description": "ID of the parent task to submit proof to",
            },
            "proof": {
                "type": "string",
                "description": "Proof of completion with concrete evidence",
            },
        },
        "required": ["parent_task_id", "proof"],
    },
)
async def submit_proof(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        api.create_comment(
            task_id=args["parent_task_id"],
            text=f"[PROOF OF COMPLETION] {args['proof']}",
            comment_type="PROPOSAL",
            created_by=_task_id,
        )
        api.update_task(_task_id, props={"aiStatus": "done"})
        return _result("Proof submitted to parent. Task marked as done.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "submit_summary",
    "Submit a summary of completed work for a top-level task (no parent). "
    "The user will review and close the task.",
    {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Summary of what was accomplished, with evidence",
            },
        },
        "required": ["summary"],
    },
)
async def submit_summary(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        api.create_comment(
            task_id=_task_id,
            text=f"[COMPLETION SUMMARY] {args['summary']}",
            created_by=_task_id,
        )
        api.update_task(_task_id, props={"aiStatus": "done"})
        return _result("Summary posted. Task marked as done. User will review and close.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "close_subtask",
    "Close a subtask after reviewing and approving its proof of completion.",
    {
        "type": "object",
        "properties": {
            "subtask_id": {
                "type": "string",
                "description": "ID of the subtask to close",
            },
            "feedback": {
                "type": "string",
                "description": "Brief feedback on the work (optional)",
            },
        },
        "required": ["subtask_id"],
    },
)
async def close_subtask(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        subtask_id = args["subtask_id"]
        feedback = args.get("feedback")

        if feedback:
            api.create_comment(
                task_id=subtask_id,
                text=f"[REVIEW] {feedback}",
                created_by=_task_id,
            )

        api.update_task(subtask_id, status="CLOSED")
        return _result(f"Subtask {subtask_id} closed.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "request_rework",
    "Reject a subtask's proof and send it back for rework with feedback.",
    {
        "type": "object",
        "properties": {
            "subtask_id": {
                "type": "string",
                "description": "ID of the subtask to send back",
            },
            "feedback": {
                "type": "string",
                "description": "What needs to be fixed or improved",
            },
        },
        "required": ["subtask_id", "feedback"],
    },
)
async def request_rework(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        subtask_id = args["subtask_id"]

        # Deny the proposal
        comments = api.list_comments(_task_id, comment_type="PROPOSAL")
        for c in comments:
            if c.created_by == subtask_id and c.proposal_status == "PENDING":
                api.deny_proposal(c.id, feedback=args["feedback"])
                break

        # Reset subtask to worker_ready so it re-runs
        api.update_task(subtask_id, props={"aiStatus": "worker_ready"})
        api.create_comment(
            task_id=subtask_id,
            text=f"[REWORK REQUESTED] {args['feedback']}",
            created_by=_task_id,
        )
        return _result(f"Subtask {subtask_id} sent back for rework.")
    except Exception as e:
        return _result(f"Error: {e}")


# ---------------------------------------------------------------------------
# SimpleAnswer tools
# ---------------------------------------------------------------------------

@tool(
    "submit_answer",
    "Submit your answer to the task. This will be posted as a comment and the task will be marked done.",
    {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "Your answer or response to the task",
            },
        },
        "required": ["answer"],
    },
)
async def submit_answer(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        api.create_comment(
            task_id=_task_id,
            text=args["answer"],
            created_by=_task_id,
        )
        api.update_task(_task_id, props={"aiStatus": "done"})
        return _result("Answer posted. Task marked as done.")
    except Exception as e:
        return _result(f"Error: {e}")


# ---------------------------------------------------------------------------
# MCP server factories
# ---------------------------------------------------------------------------

def create_dd_planner_mcp() -> Any:
    """MCP server for D&D planning mode."""
    return create_sdk_mcp_server(
        name="algo",
        version="1.0.0",
        tools=[
            mark_as_planned,
            mark_as_worker_ready,
            request_clarification,
        ],
    )


def create_dd_worker_mcp() -> Any:
    """MCP server for D&D worker mode."""
    return create_sdk_mcp_server(
        name="algo",
        version="1.0.0",
        tools=[
            submit_proof,
            submit_summary,
            request_clarification,
        ],
    )


def create_dd_manager_mcp() -> Any:
    """MCP server for D&D manager mode."""
    return create_sdk_mcp_server(
        name="algo",
        version="1.0.0",
        tools=[
            close_subtask,
            request_rework,
            submit_proof,
            submit_summary,
            request_clarification,
        ],
    )


def create_simple_answer_mcp() -> Any:
    """MCP server for SimpleAnswer algorithm."""
    return create_sdk_mcp_server(
        name="algo",
        version="1.0.0",
        tools=[
            submit_answer,
            request_clarification,
        ],
    )
