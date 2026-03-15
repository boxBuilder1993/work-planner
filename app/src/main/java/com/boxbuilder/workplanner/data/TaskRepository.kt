package com.boxbuilder.workplanner.data

import android.util.Log
import com.boxbuilder.workplanner.data.api.WorkPlannerApi
import com.boxbuilder.workplanner.data.api.dto.CreateCommentRequest
import com.boxbuilder.workplanner.data.api.dto.CreateTaskRequest
import com.boxbuilder.workplanner.data.api.dto.UpdateTaskRequest
import com.boxbuilder.workplanner.data.api.dto.UpsertRepeatingTaskRequest
import com.boxbuilder.workplanner.data.api.dto.toDomain
import com.boxbuilder.workplanner.data.api.dto.toIso
import com.boxbuilder.workplanner.data.api.dto.toIsoOrNull
import com.boxbuilder.workplanner.data.model.Comment
import com.boxbuilder.workplanner.data.model.RepeatingTask
import com.boxbuilder.workplanner.data.model.Task
import com.boxbuilder.workplanner.data.model.TaskStatus
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.map

class TaskRepository(private val api: WorkPlannerApi) {

    // ── Caches ──────────────────────────────────────────────

    private val _tasks = MutableStateFlow<Map<String, Task>>(emptyMap())
    private val _comments = MutableStateFlow<Map<String, Comment>>(emptyMap())
    private val _repeatingTasks = MutableStateFlow<Map<String, RepeatingTask>>(emptyMap())
    private val _leafTasks = MutableStateFlow<List<Task>>(emptyList())

    // ── Initialization ──────────────────────────────────────

    suspend fun initialize() {
        try {
            val rootTasks = api.getTasks(status = null).map { it.toDomain() }
            _tasks.value = rootTasks.associateBy { it.id }
            refreshLeafTasks()
        } catch (e: Exception) {
            Log.w(TAG, "Failed to initialize repository", e)
        }
    }

    // ── Task queries ────────────────────────────────────────

    fun getPendingRootTasks(): Flow<List<Task>> = _tasks.map { cache ->
        cache.values
            .filter { it.parentId == null && it.status == TaskStatus.PENDING }
            .sortedByDescending { it.createdAt }
    }

    fun getChildTasks(parentId: String): Flow<List<Task>> = _tasks.map { cache ->
        cache.values
            .filter { it.parentId == parentId }
            .sortedByDescending { it.createdAt }
    }

    fun getTaskById(taskId: String): Flow<Task?> = _tasks.map { cache ->
        cache[taskId]
    }

    fun getLeafTasks(): Flow<List<Task>> = _leafTasks

    fun searchTasks(query: String): Flow<List<Task>> = flow {
        try {
            val results = api.searchTasks(query).map { it.toDomain() }
            // Add results to cache
            val updated = _tasks.value.toMutableMap()
            results.forEach { updated[it.id] = it }
            _tasks.value = updated
            emit(results)
        } catch (e: Exception) {
            Log.w(TAG, "Search failed", e)
            emit(emptyList())
        }
    }

    suspend fun getAllTasks(): List<Task> = _tasks.value.values.toList()

    // ── Task mutations ──────────────────────────────────────

    suspend fun createTask(
        title: String,
        description: String,
        parentId: String?,
        priority: Int = 3,
        dueDate: Long? = null,
        plannedTime: Long? = null,
        duration: Double? = null
    ): Task {
        val dto = api.createTask(
            CreateTaskRequest(
                title = title,
                description = description,
                parentId = parentId,
                priority = priority,
                dueDate = dueDate.toIsoOrNull(),
                plannedTime = plannedTime.toIsoOrNull(),
                duration = duration
            )
        )
        val task = dto.toDomain()
        val updated = _tasks.value.toMutableMap()
        updated[task.id] = task
        _tasks.value = updated
        refreshLeafTasks()
        return task
    }

    suspend fun updateTask(task: Task) {
        val dto = api.updateTask(
            task.id,
            UpdateTaskRequest(
                title = task.title,
                description = task.description,
                status = task.status.name,
                priority = task.priority,
                dueDate = task.dueDate.toIsoOrNull(),
                plannedTime = task.plannedTime.toIsoOrNull(),
                duration = task.duration
            )
        )
        val updated = _tasks.value.toMutableMap()
        updated[task.id] = dto.toDomain()
        _tasks.value = updated
        refreshLeafTasks()
    }

    suspend fun closeTask(taskId: String) {
        val task = _tasks.value[taskId] ?: return
        updateTask(task.copy(status = TaskStatus.CLOSED))
    }

    suspend fun reopenTask(taskId: String) {
        val task = _tasks.value[taskId] ?: return
        updateTask(task.copy(status = TaskStatus.PENDING))
    }

    suspend fun deleteTask(taskId: String) {
        api.deleteTask(taskId)
        val updated = _tasks.value.toMutableMap()
        // Remove the task and all descendants from cache
        val toRemove = mutableSetOf(taskId)
        fun collectDescendants(id: String) {
            updated.values.filter { it.parentId == id }.forEach {
                toRemove.add(it.id)
                collectDescendants(it.id)
            }
        }
        collectDescendants(taskId)
        toRemove.forEach { updated.remove(it) }
        _tasks.value = updated

        // Also clean up comments and repeating tasks for removed tasks
        _comments.value = _comments.value.filterValues { it.taskId !in toRemove }
        _repeatingTasks.value = _repeatingTasks.value.filterKeys { it !in toRemove }

        refreshLeafTasks()
    }

    // ── Child refresh ───────────────────────────────────────

    suspend fun refreshChildren(parentId: String) {
        try {
            val children = api.getChildren(parentId).map { it.toDomain() }
            val updated = _tasks.value.toMutableMap()
            children.forEach { updated[it.id] = it }
            _tasks.value = updated
        } catch (e: Exception) {
            Log.w(TAG, "Failed to refresh children for $parentId", e)
        }
    }

    // ── Leaf tasks ──────────────────────────────────────────

    private suspend fun refreshLeafTasks() {
        try {
            val leafTasks = api.getExecutableTasks().map { it.toDomain() }
            _leafTasks.value = leafTasks
            // Also update cache
            val updated = _tasks.value.toMutableMap()
            leafTasks.forEach { updated[it.id] = it }
            _tasks.value = updated
        } catch (e: Exception) {
            Log.w(TAG, "Failed to refresh leaf tasks", e)
        }
    }

    // ── Comment queries ─────────────────────────────────────

    fun getCommentsForTask(taskId: String): Flow<List<Comment>> = _comments.map { cache ->
        cache.values
            .filter { it.taskId == taskId }
            .sortedByDescending { it.createdAt }
    }

    suspend fun fetchCommentsForTask(taskId: String) {
        try {
            val comments = api.getComments(taskId).map { it.toDomain() }
            val updated = _comments.value.toMutableMap()
            // Remove old comments for this task, add new ones
            updated.entries.removeAll { it.value.taskId == taskId }
            comments.forEach { updated[it.id] = it }
            _comments.value = updated
        } catch (e: Exception) {
            Log.w(TAG, "Failed to fetch comments for $taskId", e)
        }
    }

    // ── Comment mutations ───────────────────────────────────

    suspend fun addComment(taskId: String, text: String): Comment {
        val dto = api.createComment(taskId, CreateCommentRequest(text = text))
        val comment = dto.toDomain()
        val updated = _comments.value.toMutableMap()
        updated[comment.id] = comment
        _comments.value = updated
        return comment
    }

    suspend fun deleteComment(comment: Comment) {
        api.deleteComment(comment.id)
        val updated = _comments.value.toMutableMap()
        updated.remove(comment.id)
        _comments.value = updated
    }

    // ── Repeating task queries ──────────────────────────────

    fun getRepeatingTaskForTask(taskId: String): Flow<RepeatingTask?> = _repeatingTasks.map { cache ->
        cache[taskId]
    }

    suspend fun fetchRepeatingTask(taskId: String) {
        try {
            val dto = api.getRecurringTask(taskId)
            val repeating = dto.toDomain()
            val updated = _repeatingTasks.value.toMutableMap()
            updated[taskId] = repeating
            _repeatingTasks.value = updated
        } catch (e: Exception) {
            // 404 means no recurring task — just clear from cache
            val updated = _repeatingTasks.value.toMutableMap()
            updated.remove(taskId)
            _repeatingTasks.value = updated
        }
    }

    // ── Repeating task mutations ────────────────────────────

    suspend fun setRepeatingTask(taskId: String, intervalDays: Int, startDate: Long) {
        val dto = api.upsertRecurringTask(
            taskId,
            UpsertRepeatingTaskRequest(
                repetitionType = "interval",
                repetitionProps = mapOf(
                    "interval_days" to intervalDays.toString(),
                    "start_date" to startDate.toIso()
                )
            )
        )
        val repeating = dto.toDomain()
        val updated = _repeatingTasks.value.toMutableMap()
        updated[taskId] = repeating
        _repeatingTasks.value = updated
    }

    suspend fun removeRepeatingTask(taskId: String) {
        api.deleteRecurringTask(taskId)
        val updated = _repeatingTasks.value.toMutableMap()
        updated.remove(taskId)
        _repeatingTasks.value = updated
    }

    // ── Hierarchy helpers ───────────────────────────────────

    suspend fun getBreadcrumbs(taskId: String): List<Task> {
        return try {
            api.getBreadcrumbs(taskId).map { it.toDomain() }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to fetch breadcrumbs for $taskId", e)
            // Fallback: walk cache
            val crumbs = mutableListOf<Task>()
            var currentId: String? = taskId
            while (currentId != null) {
                val task = _tasks.value[currentId] ?: break
                crumbs.add(0, task)
                currentId = task.parentId
            }
            crumbs
        }
    }

    // ── Clear ───────────────────────────────────────────────

    fun clearAll() {
        _tasks.value = emptyMap()
        _comments.value = emptyMap()
        _repeatingTasks.value = emptyMap()
        _leafTasks.value = emptyList()
    }

    companion object {
        private const val TAG = "TaskRepository"
    }
}
