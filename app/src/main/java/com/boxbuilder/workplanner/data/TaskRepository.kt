package com.boxbuilder.workplanner.data

import com.boxbuilder.workplanner.data.dao.CommentDao
import com.boxbuilder.workplanner.data.dao.TaskDao
import com.boxbuilder.workplanner.data.entity.CommentEntity
import com.boxbuilder.workplanner.data.entity.TaskEntity
import com.boxbuilder.workplanner.data.mapper.toDomain
import com.boxbuilder.workplanner.data.mapper.toEntity
import com.boxbuilder.workplanner.data.model.Comment
import com.boxbuilder.workplanner.data.model.Task
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

class TaskRepository(
    private val taskDao: TaskDao,
    private val commentDao: CommentDao
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
        dueDate: Long? = null
    ): Task {
        val entity = TaskEntity(
            title = title,
            description = description,
            parentId = parentId,
            priority = priority,
            dueDate = dueDate
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
