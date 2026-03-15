package com.boxbuilder.workplanner.data.api

import com.boxbuilder.workplanner.data.api.dto.AuthRequest
import com.boxbuilder.workplanner.data.api.dto.AuthResponse
import com.boxbuilder.workplanner.data.api.dto.CommentDto
import com.boxbuilder.workplanner.data.api.dto.CreateCommentRequest
import com.boxbuilder.workplanner.data.api.dto.CreateTaskRequest
import com.boxbuilder.workplanner.data.api.dto.ProposalFeedbackRequest
import com.boxbuilder.workplanner.data.api.dto.RepeatingTaskDto
import com.boxbuilder.workplanner.data.api.dto.TaskDto
import com.boxbuilder.workplanner.data.api.dto.UpdateTaskRequest
import com.boxbuilder.workplanner.data.api.dto.UpsertRepeatingTaskRequest
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

interface WorkPlannerApi {

    // ── Auth ────────────────────────────────────────────────

    @POST("auth/google")
    suspend fun authGoogle(@Body request: AuthRequest): AuthResponse

    // ── Tasks ───────────────────────────────────────────────

    @GET("api/tasks")
    suspend fun getTasks(@Query("status") status: String? = null): List<TaskDto>

    @GET("api/tasks/{id}")
    suspend fun getTask(@Path("id") id: String): TaskDto

    @POST("api/tasks")
    suspend fun createTask(@Body request: CreateTaskRequest): TaskDto

    @PATCH("api/tasks/{id}")
    suspend fun updateTask(@Path("id") id: String, @Body request: UpdateTaskRequest): TaskDto

    @DELETE("api/tasks/{id}")
    suspend fun deleteTask(@Path("id") id: String)

    @GET("api/tasks/{id}/children")
    suspend fun getChildren(@Path("id") id: String): List<TaskDto>

    @GET("api/tasks/{id}/breadcrumbs")
    suspend fun getBreadcrumbs(@Path("id") id: String): List<TaskDto>

    @GET("api/tasks/executable")
    suspend fun getExecutableTasks(): List<TaskDto>

    @GET("api/tasks/search")
    suspend fun searchTasks(@Query("q") query: String): List<TaskDto>

    // ── Comments ────────────────────────────────────────────

    @GET("api/tasks/{taskId}/comments")
    suspend fun getComments(@Path("taskId") taskId: String): List<CommentDto>

    @POST("api/tasks/{taskId}/comments")
    suspend fun createComment(
        @Path("taskId") taskId: String,
        @Body request: CreateCommentRequest
    ): CommentDto

    @DELETE("api/comments/{id}")
    suspend fun deleteComment(@Path("id") id: String)

    @POST("api/comments/{id}/approve")
    suspend fun approveProposal(
        @Path("id") id: String,
        @Body request: ProposalFeedbackRequest
    ): CommentDto

    @POST("api/comments/{id}/deny")
    suspend fun denyProposal(
        @Path("id") id: String,
        @Body request: ProposalFeedbackRequest
    ): CommentDto

    // ── Recurring Tasks ─────────────────────────────────────

    @GET("api/tasks/{taskId}/recurring")
    suspend fun getRecurringTask(@Path("taskId") taskId: String): RepeatingTaskDto

    @PUT("api/tasks/{taskId}/recurring")
    suspend fun upsertRecurringTask(
        @Path("taskId") taskId: String,
        @Body request: UpsertRepeatingTaskRequest
    ): RepeatingTaskDto

    @DELETE("api/tasks/{taskId}/recurring")
    suspend fun deleteRecurringTask(@Path("taskId") taskId: String)
}
