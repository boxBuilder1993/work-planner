package com.boxbuilder.workplanner.data.api.dto

// ── Auth ────────────────────────────────────────────────────

data class AuthRequest(val idToken: String)

data class AuthResponse(
    val token: String,
    val user: UserDto
)

data class UserDto(
    val id: String,
    val email: String,
    val name: String
)

// ── Tasks ───────────────────────────────────────────────────

data class TaskDto(
    val id: String,
    val parentId: String?,
    val title: String,
    val description: String,
    val status: String,
    val priority: Int,
    val dueDate: String?,
    val taskDate: String?,
    val plannedTime: String?,
    val duration: Double?,
    val aiEnabled: Boolean = false,
    val createdAt: String,
    val updatedAt: String
)

data class CreateTaskRequest(
    val title: String,
    val description: String = "",
    val parentId: String? = null,
    val priority: Int = 3,
    val dueDate: String? = null,
    val plannedTime: String? = null,
    val duration: Double? = null,
    val aiEnabled: Boolean? = null
)

data class UpdateTaskRequest(
    val title: String? = null,
    val description: String? = null,
    val status: String? = null,
    val priority: Int? = null,
    val dueDate: String? = null,
    val plannedTime: String? = null,
    val duration: Double? = null,
    val aiEnabled: Boolean? = null
)

// ── Comments ────────────────────────────────────────────────

data class CommentDto(
    val id: String,
    val taskId: String,
    val text: String,
    val parentCommentId: String? = null,
    val commentType: String = "COMMENT",
    val createdBy: String = "user",
    val proposalStatus: String? = null,
    val proposalFeedback: String? = null,
    val createdAt: String,
    val updatedAt: String
)

data class CreateCommentRequest(val text: String)

data class ProposalFeedbackRequest(val feedback: String = "")

// ── Repeating Tasks ─────────────────────────────────────────

data class RepeatingTaskDto(
    val id: String,
    val taskId: String,
    val repetitionType: String,
    val repetitionProps: Map<String, String>,
    val createdAt: String,
    val updatedAt: String
)

data class UpsertRepeatingTaskRequest(
    val repetitionType: String = "interval",
    val repetitionProps: Map<String, String>
)
