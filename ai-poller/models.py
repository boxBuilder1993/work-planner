"""Pydantic data models matching existing WorkPlanner entity schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TaskEntity(BaseModel):
    id: str
    parent_id: str | None = Field(None, alias="parentId")
    title: str = ""
    description: str = ""
    status: str = "PENDING"  # PENDING | CLOSED
    priority: int = 0
    due_date: int | None = Field(None, alias="dueDate")
    task_date: int | None = Field(None, alias="taskDate")
    created_at: int = Field(0, alias="createdAt")
    updated_at: int = Field(0, alias="updatedAt")

    model_config = {"populate_by_name": True}


class CommentEntity(BaseModel):
    id: str
    task_id: str = Field("", alias="taskId")
    text: str = ""
    created_at: int = Field(0, alias="createdAt")
    updated_at: int = Field(0, alias="updatedAt")

    model_config = {"populate_by_name": True}


class RepeatingTaskEntity(BaseModel):
    id: str
    task_id: str = Field("", alias="taskId")
    interval_days: int = Field(0, alias="intervalDays")
    start_date: int = Field(0, alias="startDate")
    last_created_at: int | None = Field(None, alias="lastCreatedAt")
    created_at: int = Field(0, alias="createdAt")
    updated_at: int = Field(0, alias="updatedAt")

    model_config = {"populate_by_name": True}


class AIState(BaseModel):
    processed_comment_ids: set[str] = Field(default_factory=set)
