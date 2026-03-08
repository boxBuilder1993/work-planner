package com.boxbuilder.workplanner.data.mapper

import com.boxbuilder.workplanner.data.entity.RepeatingTaskEntity
import com.boxbuilder.workplanner.data.model.RepeatingTask

fun RepeatingTaskEntity.toDomain() = RepeatingTask(
    id = id,
    taskId = taskId,
    intervalDays = intervalDays,
    startDate = startDate,
    lastCreatedAt = lastCreatedAt,
    createdAt = createdAt,
    updatedAt = updatedAt
)

fun RepeatingTask.toEntity() = RepeatingTaskEntity(
    id = id,
    taskId = taskId,
    intervalDays = intervalDays,
    startDate = startDate,
    lastCreatedAt = lastCreatedAt,
    createdAt = createdAt,
    updatedAt = updatedAt
)
