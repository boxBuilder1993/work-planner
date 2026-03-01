package com.boxbuilder.workplanner.data.model

data class TaskWithDetails(
    val task: Task,
    val children: List<Task>,
    val comments: List<Comment>
)
