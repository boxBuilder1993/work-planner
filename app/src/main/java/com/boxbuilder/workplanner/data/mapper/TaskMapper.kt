package com.boxbuilder.workplanner.data.mapper

import com.boxbuilder.workplanner.data.entity.TaskEntity
import com.boxbuilder.workplanner.data.model.Task
import com.boxbuilder.workplanner.data.model.TaskStatus

fun TaskEntity.toDomain() = Task(
    id = id,
    parentId = parentId,
    title = title,
    description = description,
    status = TaskStatus.valueOf(status),
    priority = priority,
    dueDate = dueDate,
    taskDate = taskDate,
    createdAt = createdAt,
    updatedAt = updatedAt
)

fun Task.toEntity() = TaskEntity(
    id = id,
    parentId = parentId,
    title = title,
    description = description,
    status = status.name,
    priority = priority,
    dueDate = dueDate,
    taskDate = taskDate,
    createdAt = createdAt,
    updatedAt = updatedAt
)
