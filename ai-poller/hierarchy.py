"""Role detection, prompt generation, and tool assignment for the agent hierarchy.

Determines whether a task's agent is a worker (leaf) or manager (has subtasks),
generates role-specific system prompts, and assigns the appropriate tool set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from models import TaskEntity, CommentEntity


# ---------------------------------------------------------------------------
# Role detection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentRole:
    """Encapsulates role info for one agent/task."""
    task: TaskEntity
    is_manager: bool
    children: list[TaskEntity]
    parent: TaskEntity | None
    breadcrumbs: list[TaskEntity]

    @property
    def role_name(self) -> str:
        return "manager" if self.is_manager else "worker"


def detect_role(
    task: TaskEntity,
    all_tasks: list[TaskEntity],
    breadcrumbs: list[TaskEntity] | None = None,
) -> AgentRole:
    """Detect the role for a task based on whether it has children."""
    children = [t for t in all_tasks if t.parent_id == task.id]
    parent = next((t for t in all_tasks if t.id == task.parent_id), None) if task.parent_id else None
    return AgentRole(
        task=task,
        is_manager=len(children) > 0,
        children=children,
        parent=parent,
        breadcrumbs=breadcrumbs or [],
    )


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

_WORKER_PROMPT = """\
You are responsible for: "{title}"
{description_block}
{parent_block}
You are a worker agent. You write code, run tests, and raise PRs.
If the task is too large, create subtasks using the create_task tool and they will be
handled by other agents automatically. When you create subtasks, you become a manager.

IMPORTANT: Before taking any action, submit a proposal using the propose tool and wait
for approval. Do not write code or make changes until your proposal is approved.

When your work is complete, use submit_for_review to notify your parent agent.
If you encounter a blocker, use escalate to flag it.
{close_instruction}
You have access to:
- WorkPlanner tools for task/comment management
- Git MCP server for version control (clone, branch, commit, push)
- GitHub MCP server for PRs (create PR, check CI, read reviews)
- Built-in tools for file operations (Read, Write, Edit, Bash, Glob, Grep)

Your agent task ID is: {task_id}
Always use this as agent_task_id when creating proposals, replies, or comments.\
"""

_MANAGER_PROMPT = """\
You are responsible for: "{title}"
{parent_block}
Your subtasks:
{subtasks_block}

You are a manager agent. Your job is to:
1. Review proposals from your subtask agents — approve or deny them with feedback
2. Monitor subtask progress
3. When a subtask's work is satisfactory, close it using update_task(task_id, status="CLOSED")
4. When ALL subtasks are closed and the overall goal is met, use submit_for_review to notify your parent
{close_instruction}
Use get_pending_proposals to find proposals awaiting your review.
Use approve_proposal or deny_proposal to act on them.
Communicate with subtask agents through comments using the reply tool.

You can only see your immediate subtasks, not deeper levels.
You do NOT have access to code, git, or file tools — except update_task for closing subtasks.

Your agent task ID is: {task_id}
Always use this as agent_task_id when creating proposals, replies, or comments.\
"""


def generate_prompt(role: AgentRole) -> str:
    """Generate a role-specific system prompt for the agent."""
    task = role.task

    description_block = f"Description: {task.description}" if task.description else ""

    if role.parent:
        parent_block = f'Your parent task is: "{role.parent.title}" (ID: {role.parent.id})'
    else:
        parent_block = "This is a top-level task (no parent)."

    # Top-level tasks: user is the parent, agent leaves it open for user to close
    if role.parent is None:
        close_instruction = (
            "\nThis is a top-level task. The user is your manager. When your work is complete, "
            "post a comment summarizing what you did using add_comment. "
            "Do NOT close this task — the user will review and close it themselves.\n"
        )
    else:
        close_instruction = ""

    if role.is_manager:
        subtask_lines = []
        for child in role.children:
            subtask_lines.append(f"- {child.title} (status: {child.status}, ID: {child.id})")
        subtasks_block = "\n".join(subtask_lines) if subtask_lines else "- (no subtasks yet)"

        return _MANAGER_PROMPT.format(
            title=task.title,
            parent_block=parent_block,
            subtasks_block=subtasks_block,
            close_instruction=close_instruction,
            task_id=task.id,
        )
    else:
        return _WORKER_PROMPT.format(
            title=task.title,
            description_block=description_block,
            parent_block=parent_block,
            close_instruction=close_instruction,
            task_id=task.id,
        )


# ---------------------------------------------------------------------------
# Tool assignment
# ---------------------------------------------------------------------------

def get_tools_for_role(
    role: AgentRole,
    github_token: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """Return (mcp_servers, allowed_tools) based on role.

    Args:
        role: The agent's detected role.
        github_token: GitHub PAT for the GitHub MCP server.

    Returns:
        Tuple of (mcp_servers dict, allowed_tools list).
    """
    # All agents get workplanner MCP tools
    mcp_servers: dict[str, Any] = {}  # workplanner is added by spawner
    allowed_tools = ["mcp__workplanner__*"]

    if not role.is_manager:
        # Workers get code tools
        mcp_servers["git"] = {
            "command": "npx",
            "args": ["-y", "git-mcp-server"],
        }
        if github_token:
            mcp_servers["github"] = {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": github_token},
            }
        allowed_tools += [
            "mcp__git__*",
            "mcp__github__*",
            "Read", "Write", "Edit", "Bash", "Glob", "Grep",
        ]

    return mcp_servers, allowed_tools


# ---------------------------------------------------------------------------
# Helpers for poll cycle logic
# ---------------------------------------------------------------------------

def get_pending_proposals_for_task(
    task: TaskEntity,
    comments: list[CommentEntity],
) -> list[CommentEntity]:
    """Get PROPOSAL comments on this task with status PENDING (submitted BY this task's agent)."""
    return [
        c for c in comments
        if c.task_id == task.id
        and c.comment_type == "PROPOSAL"
        and c.proposal_status == "PENDING"
        and c.created_by == task.id  # created by this task's own agent
    ]


def get_approved_proposals_for_task(
    task: TaskEntity,
    comments: list[CommentEntity],
) -> list[CommentEntity]:
    """Get recently approved proposals for this task's agent."""
    return [
        c for c in comments
        if c.task_id == task.id
        and c.comment_type == "PROPOSAL"
        and c.proposal_status == "APPROVED"
        and c.created_by == task.id
    ]


def has_unreviewed_child_proposals(
    task: TaskEntity,
    all_tasks: list[TaskEntity],
    comments: list[CommentEntity],
) -> bool:
    """Check if any child task has pending proposals that need manager review."""
    child_ids = {t.id for t in all_tasks if t.parent_id == task.id}
    for c in comments:
        if (c.task_id == task.id
                and c.comment_type == "PROPOSAL"
                and c.proposal_status == "PENDING"
                and c.created_by in child_ids):
            return True
    return False


def is_new_unprocessed_task(
    task: TaskEntity,
    comments: list[CommentEntity],
    processed_task_ids: set[str],
) -> bool:
    """Check if a task needs an agent spawned.

    A task is eligible if it has no pending or approved proposals
    (those are handled by earlier checks in the processor) and either:
    - Has never been processed, OR
    - Was processed before but has no active proposals (stuck/failed agent)
    """
    # If in processed set AND has agent comments, it's already been handled
    has_agent_comments = any(
        c.task_id == task.id and c.created_by == task.id
        for c in comments
    )
    if task.id in processed_task_ids and has_agent_comments:
        # Check if the agent left the task in a stuck state:
        # no pending/approved proposals means the agent failed or timed out
        has_any_proposal = any(
            c.task_id == task.id
            and c.created_by == task.id
            and c.comment_type == "PROPOSAL"
            and c.proposal_status in ("PENDING", "APPROVED")
            for c in comments
        )
        if has_any_proposal:
            return False
        # Agent ran but left no actionable proposals → re-process
        return True
    return True
