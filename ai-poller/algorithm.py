"""Algorithm framework for the AI poller.

Each algorithm controls the full lifecycle of an ai-enabled task:
when to spawn agents, what prompt/tools they get, and how to
transition state after each run.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from models import TaskEntity, CommentEntity


# ---------------------------------------------------------------------------
# Context passed to algorithms
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskContext:
    """Everything an algorithm needs to make decisions about a task."""
    task: TaskEntity
    comments: list[CommentEntity]
    children: list[TaskEntity]
    parent: TaskEntity | None
    # Comments on each child task, keyed by child task ID
    children_comments: dict[str, list[CommentEntity]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Algorithm outputs
# ---------------------------------------------------------------------------

@dataclass
class PropsUpdate:
    """Props changes to apply after an agent run."""
    self_props: dict[str, Any]
    child_props: dict[str, Any] | None = None  # applied to newly created children


@dataclass
class SpawnPlan:
    """Everything the poller needs to run an agent."""
    prompt: str
    tools: tuple[dict[str, Any], list[str]]  # (mcp_servers, allowed_tools)
    on_complete: Callable[[TaskContext, str], PropsUpdate | None]
    model: str = "claude-sonnet-4-6"  # subscription-based, no per-token cost
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Algorithm(ABC):
    """Base class for task execution algorithms."""
    name: str

    @abstractmethod
    def evaluate(self, ctx: TaskContext, is_running: bool) -> SpawnPlan | None:
        """Evaluate a task and return a spawn plan, or None if no action needed."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class AlgorithmRegistry:
    """Maps algorithm names to handler instances."""

    def __init__(self) -> None:
        self._algorithms: dict[str, Algorithm] = {}
        self._default: str = "simple_answer"

    def register(self, algo: Algorithm) -> None:
        self._algorithms[algo.name] = algo

    def get(self, name: str) -> Algorithm:
        return self._algorithms.get(name, self._algorithms[self._default])

    def set_default(self, name: str) -> None:
        self._default = name


# ---------------------------------------------------------------------------
# Helpers shared across algorithms
# ---------------------------------------------------------------------------

def format_comment_history(comments: list[CommentEntity]) -> str:
    """Format comments as a readable history block for injection into prompts."""
    if not comments:
        return "(no previous activity)"
    lines = []
    for c in comments:
        author = "user" if c.created_by == "user" else f"agent:{c.created_by[:8]}"
        prefix = ""
        if c.comment_type == "PROPOSAL":
            status = c.proposal_status or "UNKNOWN"
            prefix = f"[PROPOSAL:{status}] "
        lines.append(f"[{author}] {prefix}{c.text}")
    return "\n---\n".join(lines)


def find_pending_proposals(ctx: TaskContext) -> list[CommentEntity]:
    """Find PENDING proposals on this task created by its own agent."""
    return [
        c for c in ctx.comments
        if c.comment_type == "PROPOSAL"
        and c.proposal_status == "PENDING"
        and c.created_by == ctx.task.id
    ]


def find_approved_proposals(ctx: TaskContext) -> list[CommentEntity]:
    """Find APPROVED proposals on this task created by its own agent."""
    return [
        c for c in ctx.comments
        if c.comment_type == "PROPOSAL"
        and c.proposal_status == "APPROVED"
        and c.created_by == ctx.task.id
    ]


def find_denied_proposals(ctx: TaskContext) -> list[CommentEntity]:
    """Find DENIED proposals on this task created by its own agent."""
    return [
        c for c in ctx.comments
        if c.comment_type == "PROPOSAL"
        and c.proposal_status == "DENIED"
        and c.created_by == ctx.task.id
    ]


def find_pending_child_proposals(ctx: TaskContext) -> list[tuple[TaskEntity, CommentEntity]]:
    """Find PENDING proposals on children's tasks (posted by children's own agents).

    Returns list of (child_task, proposal_comment) tuples.
    """
    results = []
    for child in ctx.children:
        child_comments = ctx.children_comments.get(child.id, [])
        for c in child_comments:
            if (c.comment_type == "PROPOSAL"
                    and c.proposal_status == "PENDING"
                    and c.created_by == child.id):
                results.append((child, c))
    return results


def has_proposal_resolved(ctx: TaskContext) -> bool:
    """Check if the task's most recent PENDING proposal has been resolved."""
    proposals = [
        c for c in ctx.comments
        if c.comment_type == "PROPOSAL"
        and c.created_by == ctx.task.id
    ]
    if not proposals:
        return False
    latest = max(proposals, key=lambda c: c.created_at)
    return latest.proposal_status in ("APPROVED", "DENIED")


def has_new_user_reply(ctx: TaskContext) -> bool:
    """Check if the user posted a comment after the last agent comment."""
    agent_comments = [c for c in ctx.comments if c.created_by == ctx.task.id]
    user_comments = [c for c in ctx.comments if c.created_by == "user"]
    if not user_comments:
        return False
    if not agent_comments:
        return True
    return user_comments[-1].created_at > agent_comments[-1].created_at
