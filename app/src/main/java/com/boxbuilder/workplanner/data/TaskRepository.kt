package com.boxbuilder.workplanner.data

import com.boxbuilder.workplanner.data.dao.CommentDao
import com.boxbuilder.workplanner.data.dao.RepeatingTaskDao
import com.boxbuilder.workplanner.data.dao.TaskDao
import com.boxbuilder.workplanner.data.entity.CommentEntity
import com.boxbuilder.workplanner.data.entity.RepeatingTaskEntity
import com.boxbuilder.workplanner.data.entity.TaskEntity
import com.boxbuilder.workplanner.data.mapper.toDomain
import com.boxbuilder.workplanner.data.mapper.toEntity
import com.boxbuilder.workplanner.data.model.Comment
import com.boxbuilder.workplanner.data.model.RepeatingTask
import com.boxbuilder.workplanner.data.model.Task
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.flow.map

class TaskRepository(
    private val taskDao: TaskDao,
    private val commentDao: CommentDao,
    private val repeatingTaskDao: RepeatingTaskDao
) {

    // ── Task queries ─────────────────────────────────────────

    fun getRootTasks(): Flow<List<Task>> =
        taskDao.getRootTasks().map { list -> list.map { it.toDomain() } }

    fun getPendingRootTasks(): Flow<List<Task>> =
        taskDao.getPendingRootTasks().map { list -> list.map { it.toDomain() } }

    fun getChildTasks(parentId: String): Flow<List<Task>> =
        taskDao.getChildTasks(parentId).map { list -> list.map { it.toDomain() } }

    fun getTaskById(taskId: String): Flow<Task?> =
        taskDao.getTaskById(taskId).map { it?.toDomain() }

    fun getChildCount(taskId: String): Flow<Int> =
        taskDao.getChildCount(taskId)

    fun getLeafTasks(): Flow<List<Task>> =
        taskDao.getLeafTasks().map { list -> list.map { it.toDomain() } }

    fun searchTasks(query: String): Flow<List<Task>> =
        taskDao.searchTasks(query).map { list -> list.map { it.toDomain() } }

    suspend fun getAllTasks(): List<Task> =
        taskDao.getAllTasks().map { it.toDomain() }

    // ── Task mutations ───────────────────────────────────────

    suspend fun createTask(
        title: String,
        description: String,
        parentId: String?,
        priority: Int = 3,
        dueDate: Long? = null,
        plannedTime: Long? = null,
        duration: Double? = null
    ): Task {
        val entity = TaskEntity(
            title = title,
            description = description,
            parentId = parentId,
            priority = priority,
            dueDate = dueDate,
            plannedTime = plannedTime,
            duration = duration
        )
        taskDao.insertTask(entity)
        return entity.toDomain()
    }

    suspend fun updateTask(task: Task) {
        taskDao.updateTask(task.toEntity().copy(updatedAt = System.currentTimeMillis()))
    }

    suspend fun closeTask(taskId: String) {
        val task = taskDao.getTaskByIdOnce(taskId) ?: return
        taskDao.updateTask(task.copy(
            status = "CLOSED",
            updatedAt = System.currentTimeMillis()
        ))
    }

    suspend fun reopenTask(taskId: String) {
        val task = taskDao.getTaskByIdOnce(taskId) ?: return
        taskDao.updateTask(task.copy(
            status = "PENDING",
            updatedAt = System.currentTimeMillis()
        ))
    }

    suspend fun reparentTask(taskId: String, newParentId: String?) {
        val task = taskDao.getTaskByIdOnce(taskId) ?: return
        taskDao.updateTask(task.copy(
            parentId = newParentId,
            updatedAt = System.currentTimeMillis()
        ))
    }

    suspend fun deleteTask(taskId: String) {
        taskDao.deleteTaskById(taskId)
    }

    // ── Comment queries ──────────────────────────────────────

    fun getCommentsForTask(taskId: String): Flow<List<Comment>> =
        commentDao.getCommentsForTask(taskId).map { list -> list.map { it.toDomain() } }

    // ── Comment mutations ────────────────────────────────────

    suspend fun addComment(taskId: String, text: String): Comment {
        val entity = CommentEntity(taskId = taskId, text = text)
        commentDao.insertComment(entity)
        return entity.toDomain()
    }

    suspend fun deleteComment(comment: Comment) {
        commentDao.deleteComment(comment.toEntity())
    }

    // ── Repeating task queries ────────────────────────────────

    fun getRepeatingTaskForTask(taskId: String): Flow<RepeatingTask?> =
        repeatingTaskDao.getByTaskId(taskId).map { it?.toDomain() }

    suspend fun getAllRepeatingTasks(): List<RepeatingTaskEntity> =
        repeatingTaskDao.getAll()

    // ── Repeating task mutations ─────────────────────────────

    suspend fun setRepeatingTask(taskId: String, intervalDays: Int, startDate: Long) {
        val existing = repeatingTaskDao.getByTaskId(taskId).firstOrNull()
        if (existing != null) {
            repeatingTaskDao.update(
                existing.copy(
                    intervalDays = intervalDays,
                    startDate = startDate,
                    updatedAt = System.currentTimeMillis()
                )
            )
        } else {
            repeatingTaskDao.insert(
                RepeatingTaskEntity(
                    taskId = taskId,
                    intervalDays = intervalDays,
                    startDate = startDate
                )
            )
        }
    }

    suspend fun removeRepeatingTask(taskId: String) {
        repeatingTaskDao.deleteByTaskId(taskId)
    }

    // ── Hierarchy helpers ────────────────────────────────────

    suspend fun getBreadcrumbs(taskId: String): List<Task> {
        val crumbs = mutableListOf<Task>()
        var currentId: String? = taskId
        while (currentId != null) {
            val task = taskDao.getTaskByIdOnce(currentId) ?: break
            crumbs.add(0, task.toDomain())
            currentId = task.parentId
        }
        return crumbs
    }
}
