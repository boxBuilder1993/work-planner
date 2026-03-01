package com.boxbuilder.workplanner.data.mapper

import com.boxbuilder.workplanner.data.entity.CommentEntity
import com.boxbuilder.workplanner.data.model.Comment

fun CommentEntity.toDomain() = Comment(
    id = id,
    taskId = taskId,
    text = text,
    createdAt = createdAt,
    updatedAt = updatedAt
)

fun Comment.toEntity() = CommentEntity(
    id = id,
    taskId = taskId,
    text = text,
    createdAt = createdAt,
    updatedAt = updatedAt
)
