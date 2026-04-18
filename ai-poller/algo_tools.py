"""Algorithm-specific MCP tools for state transitions.

All proposals live on the task's own comment thread. Parents watch
their children's tasks for proposals to review.

Uses contextvars for per-agent-run context instead of globals to
avoid concurrency bugs when multiple agents run in parallel.
"""

from __future__ import annotations

import contextvars
import logging
import time
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from api_client import ApiClient

logger = logging.getLogger("algo_tools")

# ---------------------------------------------------------------------------
# Per-agent context using contextvars (safe for concurrent async tasks)
# ---------------------------------------------------------------------------

_ctx_api: contextvars.ContextVar[ApiClient | None] = contextvars.ContextVar("_ctx_api", default=None)
_ctx_task_id: contextvars.ContextVar[str] = contextvars.ContextVar("_ctx_task_id", default="")
_ctx_ai_status: contextvars.ContextVar[str] = contextvars.ContextVar("_ctx_ai_status", default="")


def set_algo_context(api: ApiClient, task_id: str, ai_status: str = "") -> None:
    _ctx_api.set(api)
    _ctx_task_id.set(task_id)
    _ctx_ai_status.set(ai_status)


def _client() -> ApiClient:
    api = _ctx_api.get()
    if api is None:
        raise RuntimeError("Algo context not set — call set_algo_context() first")
    return api


def _task_id() -> str:
    return _ctx_task_id.get()


def _ai_status() -> str:
    return _ctx_ai_status.get()


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
    task_id = _task_id()
    logger.info("propose_plan called for task %s", task_id)
    try:
        api = _client()
        # Guard against concurrent proposals: re-check for existing PENDING proposals
        # right before posting. This catches the race where two agents were spawned in
        # the same poller cycle (before either posted), both passed the spawn-time check,
        # and now both try to propose. The first one wins; the second skips gracefully.
        existing_comments = api.list_comments(task_id)
        existing_pending = [
            c for c in existing_comments
            if c.comment_type == "PROPOSAL" and c.proposal_status == "PENDING"
        ]
        if existing_pending:
            logger.info(
                "Task %s: skipping propose_plan — %d PENDING proposal(s) already exist",
                task_id, len(existing_pending),
            )
            return _result(
                "Skipping: a pending proposal already exists for this task. "
                "Waiting for the existing proposal to be reviewed."
            )
        comment = api.create_comment(
            task_id=task_id,
            text=f"[PLAN PROPOSAL] {args['plan']}",
            comment_type="PROPOSAL",
            created_by=task_id,
        )
        logger.info("Comment created: %s on task %s", comment.id, task_id)
        api.update_task(task_id, props={"aiStatus": "propose"})
        logger.info("Task %s aiStatus set to propose", task_id)
        return _result("Plan proposed. Waiting for approval from parent/user.")
    except Exception as e:
        logger.exception("propose_plan failed for task %s", task_id)
        return _result(f"Error: {e}")


@tool(
    "request_clarification",
    "Ask your parent (or the user) a question. Posts a COMMENT on your own task "
    "and pauses until the user replies. Resumes automatically when a reply is posted.",
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
    task_id = _task_id()
    try:
        api = _client()
        api.create_comment(
            task_id=task_id,
            text=f"[QUESTION] {args['question']}",
            comment_type="COMMENT",
            created_by=task_id,
        )
        # Managers stay in managing/in_progress — they can keep reviewing children
        current = _ai_status()
        if current in ("in_progress", "managing", "manage"):
            return _result("Question posted to parent. Continuing management duties.")
        api.update_task(task_id, props={"aiStatus": "awaiting_input", "resumeState": current})
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
    task_id = _task_id()
    try:
        api = _client()
        api.create_comment(
            task_id=task_id,
            text=f"[PLANNING COMPLETE] {args['summary']}",
            created_by=task_id,
        )
        api.update_task(task_id, props={"aiStatus": "manage"})

        children = api.list_children(task_id)
        for child in children:
            if not child.props.get("algorithm"):
                api.update_task(child.id, props={
                    "algorithm": "decompose_and_delegate",
                    "aiStatus": "propose",
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
    task_id = _task_id()
    try:
        api = _client()
        api.create_comment(
            task_id=task_id,
            text=f"[WORKER READY] {args['reason']}",
            created_by=task_id,
        )
        api.update_task(task_id, props={"aiStatus": "propose"})
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
    task_id = _task_id()
    try:
        api = _client()
        api.create_comment(
            task_id=task_id,
            text=f"[WORK PROPOSAL] {args['plan']}",
            comment_type="PROPOSAL",
            created_by=task_id,
        )
        api.update_task(task_id, props={"aiStatus": "propose"})
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
    task_id = _task_id()
    try:
        api = _client()
        api.create_comment(
            task_id=task_id,
            text=f"[PROOF OF COMPLETION] {args['proof']}",
            comment_type="PROPOSAL",
            created_by=task_id,
        )
        api.update_task(task_id, props={"aiStatus": "proof_submitted"})
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
    task_id = _task_id()
    try:
        api = _client()
        api.create_comment(
            task_id=task_id,
            text=f"[COMPLETION SUMMARY] {args['summary']}",
            comment_type="PROPOSAL",
            created_by=task_id,
        )
        api.update_task(task_id, props={"aiStatus": "proof_submitted"})
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
        # Approval → child executes (regardless of previous status)
        api.update_task(comment.task_id, props={"aiStatus": "execute"})
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
        child_task = api.get_task(comment.task_id)
        child_status = child_task.props.get("aiStatus", "")
        # Denial → child re-proposes (regardless of previous status)
        api.update_task(comment.task_id, props={"aiStatus": "propose"})
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
    task_id = _task_id()
    try:
        api = _client()
        subtask_id = args["subtask_id"]
        feedback = args.get("feedback")
        if feedback:
            api.create_comment(
                task_id=subtask_id,
                text=f"[REVIEW] {feedback}",
                created_by=task_id,
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
        api.update_task(args["subtask_id"], props={"aiStatus": "propose"})
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
    task_id = _task_id()
    try:
        api = _client()
        api.create_comment(
            task_id=task_id,
            text=args["answer"],
            created_by=task_id,
        )
        api.update_task(task_id, props={"aiStatus": "done"})
        return _result("Answer posted. Task done.")
    except Exception as e:
        return _result(f"Error: {e}")


# ---------------------------------------------------------------------------
# MCP server factories
# ---------------------------------------------------------------------------

def create_planning_mcp() -> Any:
    return create_sdk_mcp_server(
        name="algo", version="1.0.0",
        tools=[propose_plan, request_clarification],
    )


def create_plan_execution_mcp() -> Any:
    return create_sdk_mcp_server(
        name="algo", version="1.0.0",
        tools=[mark_as_planned, mark_as_worker_ready],
    )


def create_worker_propose_mcp() -> Any:
    return create_sdk_mcp_server(
        name="algo", version="1.0.0",
        tools=[propose_work, request_clarification],
    )


def create_worker_execute_mcp() -> Any:
    return create_sdk_mcp_server(
        name="algo", version="1.0.0",
        tools=[submit_proof, submit_summary, request_clarification],
    )


def create_manager_mcp() -> Any:
    return create_sdk_mcp_server(
        name="algo", version="1.0.0",
        tools=[
            approve_child_proposal, deny_child_proposal,
            close_subtask, request_rework,
            submit_proof, submit_summary, request_clarification,
        ],
    )


def create_simple_answer_mcp() -> Any:
    return create_sdk_mcp_server(
        name="algo", version="1.0.0",
        tools=[submit_answer, request_clarification],
    )


# ---------------------------------------------------------------------------
# Orchestrated algorithm tools
# ---------------------------------------------------------------------------

@tool(
    "dispatch_worker",
    "Dispatch a worker agent to execute specific instructions on this task. "
    "Only call when you know exactly what needs to be done — specific files, "
    "commands, and deliverables. The worker will run on the next poll cycle "
    "and post its result as a comment.",
    {
        "type": "object",
        "properties": {
            "instructions": {
                "type": "string",
                "description": (
                    "Clear, specific instructions for the worker: what to implement, "
                    "which files/repos, what commands to run, what the deliverable is."
                ),
            },
        },
        "required": ["instructions"],
    },
)
async def dispatch_worker(args: dict[str, Any]) -> dict[str, Any]:
    task_id = _task_id()
    try:
        api = _client()
        instructions = args["instructions"]
        api.create_comment(
            task_id=task_id,
            text=f"[WORKER DISPATCHED] {instructions}",
            created_by=task_id,
        )
        api.update_task(task_id, props={
            "aiStatus": "worker_running",
            "workerInstructions": instructions,
            "workerStartedAt": int(time.time() * 1000),
        })
        return _result("Worker dispatched. It will execute on the next poll cycle and post its result as a comment.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "report_complete",
    "Report that your work is done. Posts your result as a comment and hands "
    "control back to the orchestrator.",
    {
        "type": "object",
        "properties": {
            "result": {
                "type": "string",
                "description": (
                    "What you did and evidence: PR links, file paths, "
                    "command output, test results, or a description of what was done. "
                    "If blocked, describe what you tried and where you got stuck."
                ),
            },
        },
        "required": ["result"],
    },
)
async def report_complete(args: dict[str, Any]) -> dict[str, Any]:
    task_id = _task_id()
    try:
        api = _client()
        api.create_comment(
            task_id=task_id,
            text=f"[WORKER COMPLETE] {args['result']}",
            created_by=task_id,
        )
        api.update_task(task_id, props={"aiStatus": "orchestrating"})
        return _result("Result posted. Orchestrator will review on the next cycle.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "mark_orchestrated_done",
    "Mark this task as complete. Posts a summary for the user to review. "
    "The user (or parent task) will close the task when satisfied.",
    {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "What was accomplished, with links to PRs, commits, or other evidence.",
            },
        },
        "required": ["summary"],
    },
)
async def mark_orchestrated_done(args: dict[str, Any]) -> dict[str, Any]:
    task_id = _task_id()
    try:
        api = _client()
        api.create_comment(
            task_id=task_id,
            text=f"[COMPLETE] {args['summary']}",
            comment_type="PROPOSAL",
            created_by=task_id,
        )
        api.update_task(task_id, props={"aiStatus": "done"})
        return _result("Task marked complete. Waiting for user review.")
    except Exception as e:
        return _result(f"Error: {e}")


@tool(
    "create_subtask",
    "Create a subtask under the current task. Always sets aiEnabled=true and "
    "algorithm=orchestrated so the poller picks it up automatically.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Subtask title"},
            "description": {"type": "string", "description": "Subtask description"},
            "priority": {"type": "integer", "description": "Priority 1-5 (1=urgent)"},
        },
        "required": ["title"],
    },
)
async def create_subtask(args: dict[str, Any]) -> dict[str, Any]:
    task_id = _task_id()
    try:
        api = _client()
        body: dict[str, Any] = {
            "title": args["title"],
            "parentId": task_id,
            "aiEnabled": True,
            "props": {"algorithm": "orchestrated"},
        }
        if args.get("description"):
            body["description"] = args["description"]
        if args.get("priority") is not None:
            body["priority"] = args["priority"]
        result = api.create_task(body)
        return _result(f"Subtask created: {result.get('id')} — {args['title']}")
    except Exception as e:
        return _result(f"Error: {e}")


def create_orchestrator_mcp() -> Any:
    return create_sdk_mcp_server(
        name="algo", version="1.0.0",
        tools=[dispatch_worker, mark_orchestrated_done, close_subtask, create_subtask],
    )


def create_orchestrated_worker_mcp() -> Any:
    return create_sdk_mcp_server(
        name="algo", version="1.0.0",
        tools=[report_complete],
    )
