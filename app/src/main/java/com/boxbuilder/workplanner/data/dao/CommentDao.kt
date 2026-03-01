package com.boxbuilder.workplanner.data.dao

import com.boxbuilder.workplanner.data.entity.CommentEntity
import kotlinx.coroutines.flow.Flow

interface CommentDao {

    // ── Reactive queries ─────────────────────────────────────

    fun getCommentsForTask(taskId: String): Flow<List<CommentEntity>>

    // ── One-shot queries ─────────────────────────────────────

    suspend fun getAllComments(): List<CommentEntity>

    // ── Mutations ────────────────────────────────────────────

    suspend fun insertComment(comment: CommentEntity)

    suspend fun insertComments(comments: List<CommentEntity>)

    suspend fun deleteComment(comment: CommentEntity)

    suspend fun deleteAllComments()
}
