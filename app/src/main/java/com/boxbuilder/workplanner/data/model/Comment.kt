package com.boxbuilder.workplanner.data.model

data class Comment(
    val id: String,
    val taskId: String,
    val text: String,
    val createdAt: Long,
    val updatedAt: Long
)
