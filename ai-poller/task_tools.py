"""MCP tools for the Claude Agent SDK.

Tools call the WorkPlanner backend API directly via a shared ApiClient instance.
Set the client before each agent run via set_api_client().
"""

from __future__ import annotations

import difflib
import json
import logging
import subprocess
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from api_client import ApiClient

logger = logging.getLogger(__name__)

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


_DEDUP_SIMILARITY_THRESHOLD = 0.8


def _titles_are_similar(a: str, b: str, threshold: float = _DEDUP_SIMILARITY_THRESHOLD) -> bool:
    """Return True if two task titles are similar enough to be considered duplicates.

    Uses SequenceMatcher ratio as the primary check, and also treats one title
    being a substring of the other (modulo whitespace) as a match.
    """
    a_lower = a.lower().strip()
    b_lower = b.lower().strip()
    if a_lower == b_lower:
        return True
    ratio = difflib.SequenceMatcher(None, a_lower, b_lower).ratio()
    if ratio >= threshold:
        return True
    # Substring check: catches "Implement X" vs "Implement X in finance-scripts"
    if a_lower in b_lower or b_lower in a_lower:
        return True
    return False


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


@tool(
    "get_task_comments",
    "Get comment thread for a task, sorted chronologically. Optionally filter by comment_type.",
    {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task"},
            "comment_type": {"type": "string", "description": "Filter by type: COMMENT or PROPOSAL (optional)"},
        },
        "required": ["task_id"],
    },
)
async def get_task_comments(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comments = _client().list_comments(
            args["task_id"],
            comment_type=args.get("comment_type"),
        )
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
            "ai_enabled": {"type": "boolean", "description": "Whether AI agent processing is enabled for this task"},
        },
        "required": ["title"],
    },
)
async def create_task(args: dict[str, Any]) -> dict[str, Any]:
    try:
        client = _client()
        new_title: str = args["title"]
        parent_id: str | None = args.get("parent_id")

        # Deduplication guard: when creating a child task, check whether a
        # sibling with a sufficiently similar title already exists. This prevents
        # duplicate subtasks from being created when the plan executor re-runs
        # due to a STATUS_ALIASES bug or other retry scenario.
        if parent_id:
            try:
                existing_siblings = client.list_children(parent_id)
                for sibling in existing_siblings:
                    if sibling.status != "CLOSED" and _titles_are_similar(new_title, sibling.title):
                        logger.info(
                            "Skipping duplicate child task '%s' — similar to existing '%s' (%s)",
                            new_title, sibling.title, sibling.id,
                        )
                        return _result(
                            f"Skipped: a child task with a similar title already exists.\n"
                            f"  Existing: '{sibling.title}' (id={sibling.id})\n"
                            f"  Requested: '{new_title}'\n"
                            f"Use the existing task instead of creating a duplicate."
                        )
            except Exception as dedup_err:
                logger.warning(
                    "Deduplication check failed for parent %s; proceeding with create: %s",
                    parent_id, dedup_err,
                )

        task = client.create_task(
            title=new_title,
            description=args.get("description", ""),
            parent_id=parent_id,
            priority=args.get("priority", 0),
            due_date=args.get("due_date"),
            planned_time=args.get("planned_time"),
            duration=args.get("duration"),
            ai_enabled=args.get("ai_enabled", False),
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
    "Add a comment to a task. Supports threading, comment types, and agent attribution.",
    {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task to comment on"},
            "text": {"type": "string", "description": "Comment text"},
            "parent_comment_id": {"type": "string", "description": "ID of parent comment for threaded replies (optional)"},
            "comment_type": {"type": "string", "description": "COMMENT or PROPOSAL (default: COMMENT)"},
            "created_by": {"type": "string", "description": "Author: 'user' or an agent task ID (default: 'user')"},
        },
        "required": ["task_id", "text"],
    },
)
async def add_comment(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comment = _client().create_comment(
            task_id=args["task_id"],
            text=args["text"],
            parent_comment_id=args.get("parent_comment_id"),
            comment_type=args.get("comment_type", "COMMENT"),
            created_by=args.get("created_by", "user"),
        )
        return _result(_comment_json(comment))
    except Exception as e:
        return _result(f"Error adding comment: {e}")


# ---------------------------------------------------------------------------
# Agent hierarchy tools — proposals & reviews
# ---------------------------------------------------------------------------

@tool(
    "propose",
    "Create a PROPOSAL comment on the agent's task for the parent/manager to review. "
    "Sets comment_type=PROPOSAL and proposal_status=PENDING automatically.",
    {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task to attach the proposal to"},
            "text": {"type": "string", "description": "Proposal text describing the plan or action"},
            "agent_task_id": {"type": "string", "description": "The task ID of the agent creating this proposal (used as created_by)"},
        },
        "required": ["task_id", "text", "agent_task_id"],
    },
)
async def propose(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comment = _client().create_comment(
            task_id=args["task_id"],
            text=args["text"],
            comment_type="PROPOSAL",
            created_by=args["agent_task_id"],
        )
        return _result(_comment_json(comment))
    except Exception as e:
        return _result(f"Error creating proposal: {e}")


@tool(
    "reply",
    "Reply in a comment thread. Creates a comment with a parent_comment_id for threading.",
    {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task the comment thread belongs to"},
            "parent_comment_id": {"type": "string", "description": "ID of the comment to reply to"},
            "text": {"type": "string", "description": "Reply text"},
            "agent_task_id": {"type": "string", "description": "The task ID of the agent replying (used as created_by)"},
        },
        "required": ["task_id", "parent_comment_id", "text", "agent_task_id"],
    },
)
async def reply(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comment = _client().create_comment(
            task_id=args["task_id"],
            text=args["text"],
            parent_comment_id=args["parent_comment_id"],
            comment_type="COMMENT",
            created_by=args["agent_task_id"],
        )
        return _result(_comment_json(comment))
    except Exception as e:
        return _result(f"Error replying: {e}")


@tool(
    "get_my_proposals",
    "Get all PROPOSAL comments created by this agent on a given task.",
    {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task to check proposals on"},
            "agent_task_id": {"type": "string", "description": "The agent's task ID (filters by created_by)"},
        },
        "required": ["task_id", "agent_task_id"],
    },
)
async def get_my_proposals(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comments = _client().list_comments(args["task_id"], comment_type="PROPOSAL")
        mine = [c for c in comments if c.created_by == args["agent_task_id"]]
        return _result(json.dumps([c.model_dump() for c in mine], indent=2))
    except Exception as e:
        return _result(f"Error fetching proposals: {e}")


@tool(
    "get_pending_proposals",
    "Get unreviewed PROPOSAL comments from subtask agents (manager tool). "
    "Fetches PROPOSAL comments on the given task that have proposal_status=PENDING.",
    {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task to check for pending proposals"},
        },
        "required": ["task_id"],
    },
)
async def get_pending_proposals(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comments = _client().list_comments(args["task_id"], comment_type="PROPOSAL")
        pending = [c for c in comments if c.proposal_status == "PENDING"]
        return _result(json.dumps([c.model_dump() for c in pending], indent=2))
    except Exception as e:
        return _result(f"Error fetching pending proposals: {e}")


@tool(
    "approve_proposal",
    "Approve a pending PROPOSAL comment. Sets proposal_status=APPROVED.",
    {
        "type": "object",
        "properties": {
            "comment_id": {"type": "string", "description": "ID of the PROPOSAL comment to approve"},
        },
        "required": ["comment_id"],
    },
)
async def approve_proposal(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comment = _client().approve_proposal(args["comment_id"])
        return _result(_comment_json(comment))
    except Exception as e:
        return _result(f"Error approving proposal: {e}")


@tool(
    "deny_proposal",
    "Deny a pending PROPOSAL comment with feedback. Sets proposal_status=DENIED.",
    {
        "type": "object",
        "properties": {
            "comment_id": {"type": "string", "description": "ID of the PROPOSAL comment to deny"},
            "feedback": {"type": "string", "description": "Feedback explaining why the proposal was denied"},
        },
        "required": ["comment_id", "feedback"],
    },
)
async def deny_proposal(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comment = _client().deny_proposal(args["comment_id"], feedback=args["feedback"])
        return _result(_comment_json(comment))
    except Exception as e:
        return _result(f"Error denying proposal: {e}")


@tool(
    "submit_for_review",
    "Submit proof of completion for review by the parent/manager agent. "
    "Creates a PROPOSAL on the PARENT task so the manager can see it. "
    "Include concrete evidence: command outputs, test results, file changes, PR links.",
    {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the PARENT task (post proof here so the manager sees it)"},
            "text": {"type": "string", "description": "Proof of completion: what was done, evidence, outputs, results"},
            "agent_task_id": {"type": "string", "description": "The agent's own task ID (used as created_by)"},
        },
        "required": ["task_id", "text", "agent_task_id"],
    },
)
async def submit_for_review(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comment = _client().create_comment(
            task_id=args["task_id"],
            text=f"[SUBMIT FOR REVIEW] {args['text']}",
            comment_type="PROPOSAL",
            created_by=args["agent_task_id"],
        )
        return _result(_comment_json(comment))
    except Exception as e:
        return _result(f"Error submitting for review: {e}")


@tool(
    "escalate",
    "Escalate a blocker to the parent/manager agent. "
    "Creates a PROPOSAL comment flagging an issue that needs higher-level attention.",
    {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID of the task with the blocker"},
            "text": {"type": "string", "description": "Description of the blocker or issue"},
            "agent_task_id": {"type": "string", "description": "The agent's task ID (used as created_by)"},
        },
        "required": ["task_id", "text", "agent_task_id"],
    },
)
async def escalate(args: dict[str, Any]) -> dict[str, Any]:
    try:
        comment = _client().create_comment(
            task_id=args["task_id"],
            text=f"[ESCALATION] {args['text']}",
            comment_type="PROPOSAL",
            created_by=args["agent_task_id"],
        )
        return _result(_comment_json(comment))
    except Exception as e:
        return _result(f"Error escalating: {e}")


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
            # Agent hierarchy — proposals & reviews
            propose, reply, get_my_proposals, get_pending_proposals,
            approve_proposal, deny_proposal, submit_for_review, escalate,
            # Shell
            run_command,
        ],
    )
