package com.boxbuilder.workplanner.data.model

data class RepeatingTask(
    val id: String,
    val taskId: String,
    val intervalDays: Int,
    val startDate: Long,
    val lastCreatedAt: Long?,
    val createdAt: Long,
    val updatedAt: Long
)
