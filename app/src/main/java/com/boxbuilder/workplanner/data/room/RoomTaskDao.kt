package com.boxbuilder.workplanner.data.room

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import com.boxbuilder.workplanner.data.dao.TaskDao
import com.boxbuilder.workplanner.data.entity.TaskEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface RoomTaskDao : TaskDao {

    // ── Reactive queries ─────────────────────────────────────

    @Query("SELECT * FROM tasks WHERE parentId IS NULL ORDER BY createdAt ASC")
    override fun getRootTasks(): Flow<List<TaskEntity>>

    @Query("SELECT * FROM tasks WHERE parentId IS NULL AND status = 'PENDING' ORDER BY createdAt ASC")
    override fun getPendingRootTasks(): Flow<List<TaskEntity>>

    @Query("SELECT * FROM tasks WHERE parentId = :parentId ORDER BY createdAt ASC")
    override fun getChildTasks(parentId: String): Flow<List<TaskEntity>>

    @Query("SELECT * FROM tasks WHERE id = :id")
    override fun getTaskById(id: String): Flow<TaskEntity?>

    @Query("SELECT COUNT(*) FROM tasks WHERE parentId = :parentId")
    override fun getChildCount(parentId: String): Flow<Int>

    @Query(
        """
        SELECT * FROM tasks
        WHERE status = 'PENDING'
        AND id NOT IN (SELECT DISTINCT parentId FROM tasks WHERE parentId IS NOT NULL)
        ORDER BY priority ASC, CASE WHEN dueDate IS NULL THEN 1 ELSE 0 END, dueDate DESC
        """
    )
    override fun getLeafTasks(): Flow<List<TaskEntity>>

    @Query(
        """
        SELECT * FROM tasks
        WHERE title LIKE '%' || :query || '%'
        OR description LIKE '%' || :query || '%'
        ORDER BY createdAt ASC
        """
    )
    override fun searchTasks(query: String): Flow<List<TaskEntity>>

    // ── One-shot queries ─────────────────────────────────────

    @Query("SELECT * FROM tasks WHERE id = :id")
    override suspend fun getTaskByIdOnce(id: String): TaskEntity?

    @Query("SELECT * FROM tasks")
    override suspend fun getAllTasks(): List<TaskEntity>

    // ── Mutations ────────────────────────────────────────────

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    override suspend fun insertTask(task: TaskEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    override suspend fun insertTasks(tasks: List<TaskEntity>)

    @Update
    override suspend fun updateTask(task: TaskEntity)

    @Query("DELETE FROM tasks WHERE id = :id")
    override suspend fun deleteTaskById(id: String)

    @Query("DELETE FROM tasks")
    override suspend fun deleteAllTasks()
}
