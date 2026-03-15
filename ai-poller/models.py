"""Pydantic data models matching the WorkPlanner backend API responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class TaskEntity(BaseModel):
    id: str
    user_id: str = ""
    parent_id: str | None = None
    title: str = ""
    description: str = ""
    status: str = "PENDING"  # PENDING | IN_PROGRESS | QUEUED | CLOSED
    priority: int = 0
    due_date: int | None = None
    task_date: int | None = None
    planned_time: int | None = None
    duration: float | None = None
    ai_enabled: bool = False
    level: int | None = None
    created_at: int = 0
    updated_at: int = 0

    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
    )


class CommentEntity(BaseModel):
    id: str
    task_id: str = ""
    parent_comment_id: str | None = None
    text: str = ""
    comment_type: str = "COMMENT"  # COMMENT | PROPOSAL
    created_by: str = "user"  # "user" or agent task ID
    proposal_status: str | None = None  # PENDING | APPROVED | DENIED
    proposal_feedback: str | None = None
    created_at: int = 0
    updated_at: int = 0

    model_config = ConfigDict(
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
    )


class AIState(BaseModel):
    processed_comment_ids: set[str] = Field(default_factory=set)
