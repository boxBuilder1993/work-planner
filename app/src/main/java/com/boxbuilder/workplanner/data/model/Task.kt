package com.boxbuilder.workplanner.data.model

data class Task(
    val id: String,
    val parentId: String?,
    val title: String,
    val description: String,
    val status: TaskStatus,
    val priority: Int,
    val dueDate: Long?,
    val createdAt: Long,
    val updatedAt: Long
)
