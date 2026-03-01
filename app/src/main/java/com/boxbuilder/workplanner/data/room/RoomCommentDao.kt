package com.boxbuilder.workplanner.data.room

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.boxbuilder.workplanner.data.dao.CommentDao
import com.boxbuilder.workplanner.data.entity.CommentEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface RoomCommentDao : CommentDao {

    // ── Reactive queries ─────────────────────────────────────

    @Query("SELECT * FROM comments WHERE taskId = :taskId ORDER BY createdAt DESC")
    override fun getCommentsForTask(taskId: String): Flow<List<CommentEntity>>

    // ── One-shot queries ─────────────────────────────────────

    @Query("SELECT * FROM comments")
    override suspend fun getAllComments(): List<CommentEntity>

    // ── Mutations ────────────────────────────────────────────

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    override suspend fun insertComment(comment: CommentEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    override suspend fun insertComments(comments: List<CommentEntity>)

    @Delete
    override suspend fun deleteComment(comment: CommentEntity)

    @Query("DELETE FROM comments")
    override suspend fun deleteAllComments()
}
