package com.boxbuilder.workplanner.data.dao

import com.boxbuilder.workplanner.data.entity.TaskEntity
import kotlinx.coroutines.flow.Flow

interface TaskDao {

    // ── Reactive queries (return Flow for UI observation) ─────

    fun getRootTasks(): Flow<List<TaskEntity>>

    fun getPendingRootTasks(): Flow<List<TaskEntity>>

    fun getChildTasks(parentId: String): Flow<List<TaskEntity>>

    fun getTaskById(id: String): Flow<TaskEntity?>

    fun getChildCount(parentId: String): Flow<Int>

    fun getLeafTasks(): Flow<List<TaskEntity>>

    fun searchTasks(query: String): Flow<List<TaskEntity>>

    // ── One-shot queries (suspend, for non-UI operations) ────

    suspend fun getTaskByIdOnce(id: String): TaskEntity?

    suspend fun getAllTasks(): List<TaskEntity>

    // ── Mutations ────────────────────────────────────────────

    suspend fun insertTask(task: TaskEntity)

    suspend fun insertTasks(tasks: List<TaskEntity>)

    suspend fun updateTask(task: TaskEntity)

    suspend fun deleteTaskById(id: String)

    suspend fun deleteAllTasks()
}
