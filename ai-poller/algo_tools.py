"""Algorithm-specific MCP tools for state transitions.

All proposals live on the task's own comment thread. Parents watch
their children's tasks for proposals to review.
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
_ai_status: str = ""


def set_algo_context(api: ApiClient, task_id: str, ai_status: str = "") -> None:
    global _api, _task_id, _ai_status
    _api = api
    _task_id = task_id
    _ai_status = ai_status


def _client() -> ApiClient:
    if _api is None:
        raise RuntimeError("Algo context not set — call set_algo_context() first")
    return _api


def _result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


# ---------------------------------------------------------------------------
# Planning phase tools
# ---------------------------------------------------------------------------

@tool(
    "propose_plan",
    "Propose your plan for this task. This posts a PROPOSAL on your own task "
    "for your parent (or the user) to review. Do NOT create subtasks yet — wait for approval.",
    {
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": "Your proposed plan: what subtasks you want to create, or why this is worker-ready. Be specific about deliverables.",
            },
        },
        "required": ["plan"],
    },
)
async def propose_plan(args: dict[str, Any]) -> dict[str, Any]:
    import logging
    logger = logging.getLogger("algo_tools")
    logger.info("propose_plan called for task %s", _task_id)
    try:
        api = _client()
        logger.info("Creating PROPOSAL comment on task %s", _task_id)
        comment = api.create_comment(
            task_id=_task_id,
            text=f"[PLAN PROPOSAL] {args['plan']}",
            comment_type="PROPOSAL",
            created_by=_task_id,
        )
        logger.info("Comment created: %s", comment.id)
        api.update_task(_task_id, props={"aiStatus": "plan_proposed"})
        logger.info("Task %s aiStatus set to plan_proposed", _task_id)
        return _result("Plan proposed. Waiting for approval from parent/user.")
    except Exception as e:
        logger.exception("propose_plan failed for task %s", _task_id)
        return _result(f"Error: {e}")


@tool(
    "request_clarification",
    "Ask your parent (or the user) a question. Posts a PROPOSAL on your own task "
    "and pauses until it's answered. Your parent will see it and respond.",
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
            text=f"[QUESTION] {args['question']}",
            comment_type="PROPOSAL",
            created_by=_task_id,
        )
        # Managers stay in_progress — they can keep reviewing children
        # while waiting for an answer from their parent
        if _ai_status == "in_progress":
            return _result("Question posted to parent. Continuing management duties.")
        api.update_task(_task_id, props={"aiStatus": "awaiting_input"})
        return _result("Question posted. Task paused until parent responds.")
    except Exception as e:
        return _result(f"Error: {e}")


# ---------------------------------------------------------------------------
# Plan execution tools (available after plan approval)
# ---------------------------------------------------------------------------

@tool(
    "mark_as_planned",
    "Call this AFTER you have created all subtasks. Moves to management mode.",
    {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Brief summary of subtasks created",
            },
        },
        "required": ["summary"],
    },
)
async def mark_as_planned(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        task_id = _task_id

        api.create_comment(
            task_id=task_id,
            text=f"[PLANNING COMPLETE] {args['summary']}",
            created_by=task_id,
        )
        api.update_task(task_id, props={"aiStatus": "in_progress"})

        # Initialize children with D&D algorithm
        children = api.list_children(task_id)
        for child in children:
            if not child.props.get("algorithm"):
                api.update_task(child.id, props={
                    "algorithm": "decompose_and_delegate",
                    "aiStatus": "needs_planning",
                })

        return _result(f"Task in management mode. {len(children)} child task(s) initialized.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "mark_as_worker_ready",
    "Call this when the approved plan says this task should be implemented directly. "
    "Only for truly small tasks — one function, one bug fix, one test file.",
    {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why this task is small enough for direct implementation",
            },
        },
        "required": ["reason"],
    },
)
async def mark_as_worker_ready(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        api.create_comment(
            task_id=_task_id,
            text=f"[WORKER READY] {args['reason']}",
            created_by=_task_id,
        )
        api.update_task(_task_id, props={"aiStatus": "worker_ready"})
        return _result("Task marked as worker_ready.")
    except Exception as e:
        return _result(f"Error: {e}")


# ---------------------------------------------------------------------------
# Worker tools
# ---------------------------------------------------------------------------

@tool(
    "propose_work",
    "Propose the specific actions you want to take — PRs to open, commands to run, "
    "files to change. Posts a PROPOSAL on your own task for approval before executing.",
    {
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": "Specific actions: PRs to open, commands to run, files to create/modify. Be concrete.",
            },
        },
        "required": ["plan"],
    },
)
async def propose_work(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        api.create_comment(
            task_id=_task_id,
            text=f"[WORK PROPOSAL] {args['plan']}",
            comment_type="PROPOSAL",
            created_by=_task_id,
        )
        api.update_task(_task_id, props={"aiStatus": "work_proposed"})
        return _result("Work proposal posted. Waiting for approval before executing.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "submit_proof",
    "Submit proof of completion. Posts a PROPOSAL on your own task with evidence. "
    "Your parent will review and close your task if satisfied.",
    {
        "type": "object",
        "properties": {
            "proof": {
                "type": "string",
                "description": "Proof of completion: PR links, command outputs, test results, file changes",
            },
        },
        "required": ["proof"],
    },
)
async def submit_proof(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        api.create_comment(
            task_id=_task_id,
            text=f"[PROOF OF COMPLETION] {args['proof']}",
            comment_type="PROPOSAL",
            created_by=_task_id,
        )
        api.update_task(_task_id, props={"aiStatus": "proof_submitted"})
        return _result("Proof submitted. Waiting for parent to review and close.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "submit_summary",
    "Submit a completion summary for a top-level task (user reviews). "
    "Posts a PROPOSAL on your own task. User will close it if satisfied.",
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
            comment_type="PROPOSAL",
            created_by=_task_id,
        )
        api.update_task(_task_id, props={"aiStatus": "proof_submitted"})
        return _result("Summary posted. User will review and close.")
    except Exception as e:
        return _result(f"Error: {e}")


# ---------------------------------------------------------------------------
# Manager tools — operate on children's tasks
# ---------------------------------------------------------------------------

@tool(
    "approve_child_proposal",
    "Approve a pending proposal on a child task.",
    {
        "type": "object",
        "properties": {
            "proposal_id": {
                "type": "string",
                "description": "ID of the PROPOSAL comment to approve",
            },
        },
        "required": ["proposal_id"],
    },
)
async def approve_child_proposal(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        comment = api.approve_proposal(args["proposal_id"])
        # Transition child's state based on what was approved
        child_task = api.get_task(comment.task_id)
        child_status = child_task.props.get("aiStatus", "")
        if child_status == "plan_proposed":
            api.update_task(comment.task_id, props={"aiStatus": "plan_approved"})
        elif child_status == "work_proposed":
            api.update_task(comment.task_id, props={"aiStatus": "work_approved"})
        elif child_status == "awaiting_input":
            # Question answered — resume planning
            api.update_task(comment.task_id, props={"aiStatus": "needs_planning"})
        return _result(f"Proposal approved and child state updated.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "deny_child_proposal",
    "Deny a pending proposal on a child task with feedback.",
    {
        "type": "object",
        "properties": {
            "proposal_id": {
                "type": "string",
                "description": "ID of the PROPOSAL comment to deny",
            },
            "feedback": {
                "type": "string",
                "description": "Feedback explaining why denied or what to change",
            },
        },
        "required": ["proposal_id", "feedback"],
    },
)
async def deny_child_proposal(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        comment = api.deny_proposal(args["proposal_id"], feedback=args["feedback"])
        # Transition child back so it re-plans or re-proposes
        child_task = api.get_task(comment.task_id)
        child_status = child_task.props.get("aiStatus", "")
        if child_status == "plan_proposed":
            api.update_task(comment.task_id, props={"aiStatus": "needs_planning"})
        elif child_status == "work_proposed":
            api.update_task(comment.task_id, props={"aiStatus": "worker_ready"})
        elif child_status == "awaiting_input":
            # Question answered with feedback — resume planning
            api.update_task(comment.task_id, props={"aiStatus": "needs_planning"})
        return _result(f"Proposal denied with feedback. Child state reset.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "close_subtask",
    "Close a child task after verifying its proof of completion.",
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
    "Send a child task back for rework by denying its proof and resetting it.",
    {
        "type": "object",
        "properties": {
            "subtask_id": {
                "type": "string",
                "description": "ID of the subtask to send back",
            },
            "proposal_id": {
                "type": "string",
                "description": "ID of the proof PROPOSAL to deny",
            },
            "feedback": {
                "type": "string",
                "description": "What needs to be fixed or improved",
            },
        },
        "required": ["subtask_id", "proposal_id", "feedback"],
    },
)
async def request_rework(args: dict[str, Any]) -> dict[str, Any]:
    try:
        api = _client()
        api.deny_proposal(args["proposal_id"], feedback=args["feedback"])
        api.update_task(args["subtask_id"], props={"aiStatus": "worker_ready"})
        return _result(f"Subtask sent back for rework.")
    except Exception as e:
        return _result(f"Error: {e}")


# ---------------------------------------------------------------------------
# SimpleAnswer tools
# ---------------------------------------------------------------------------

@tool(
    "submit_answer",
    "Submit your answer to the task. Posted as a comment, task marked done.",
    {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "Your answer or response",
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
        return _result("Answer posted. Task done.")
    except Exception as e:
        return _result(f"Error: {e}")


# ---------------------------------------------------------------------------
# MCP server factories
# ---------------------------------------------------------------------------

def create_planning_mcp() -> Any:
    """Tools for planning phase: propose, ask questions. No create_task."""
    return create_sdk_mcp_server(
        name="algo",
        version="1.0.0",
        tools=[propose_plan, request_clarification],
    )


def create_plan_execution_mcp() -> Any:
    """Tools for executing an approved plan: create subtasks or mark worker-ready."""
    return create_sdk_mcp_server(
        name="algo",
        version="1.0.0",
        tools=[mark_as_planned, mark_as_worker_ready],
    )


def create_worker_propose_mcp() -> Any:
    """Tools for worker to propose its work before executing."""
    return create_sdk_mcp_server(
        name="algo",
        version="1.0.0",
        tools=[propose_work, request_clarification],
    )


def create_worker_execute_mcp() -> Any:
    """Tools for worker to execute approved work and submit proof."""
    return create_sdk_mcp_server(
        name="algo",
        version="1.0.0",
        tools=[submit_proof, submit_summary, request_clarification],
    )


def create_manager_mcp() -> Any:
    """Tools for manager: review children, close/rework, escalate, complete."""
    return create_sdk_mcp_server(
        name="algo",
        version="1.0.0",
        tools=[
            approve_child_proposal,
            deny_child_proposal,
            close_subtask,
            request_rework,
            submit_proof,
            submit_summary,
            request_clarification,
        ],
    )


def create_simple_answer_mcp() -> Any:
    """Tools for SimpleAnswer algorithm."""
    return create_sdk_mcp_server(
        name="algo",
        version="1.0.0",
        tools=[submit_answer, request_clarification],
    )
