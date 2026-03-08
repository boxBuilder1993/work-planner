package com.boxbuilder.workplanner.ui.taskdetail

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.boxbuilder.workplanner.data.TaskRepository
import com.boxbuilder.workplanner.data.model.Comment
import com.boxbuilder.workplanner.data.model.RepeatingTask
import com.boxbuilder.workplanner.data.model.Task
import com.boxbuilder.workplanner.data.model.TaskStatus
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

data class TaskDetailUiState(
    val task: Task? = null,
    val children: List<Task> = emptyList(),
    val comments: List<Comment> = emptyList(),
    val breadcrumbs: List<Task> = emptyList(),
    val repeatingTask: RepeatingTask? = null,
    val isEditing: Boolean = false,
    val isNewTask: Boolean = false,
    val isLoading: Boolean = true
)

data class EditState(
    val title: String = "",
    val description: String = "",
    val status: TaskStatus = TaskStatus.PENDING,
    val priority: Int = 3,
    val dueDate: Long? = null,
    val parentId: String? = null,
    val repeatIntervalDays: Int? = null,
    val repeatStartDate: Long? = null
)

@HiltViewModel
class TaskDetailViewModel @Inject constructor(
    private val repository: TaskRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val taskId: String? = savedStateHandle.get<String>("taskId")
        ?.takeIf { it != "new" }
    private val parentIdArg: String? = savedStateHandle.get<String>("parentId")

    private val _editState = MutableStateFlow(EditState())
    val editState: StateFlow<EditState> = _editState.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    fun clearError() {
        _errorMessage.value = null
    }

    // UI-controlled state (isEditing, breadcrumbs) — separate from reactive data
    private val _localState = MutableStateFlow(
        LocalState(isEditing = taskId == null, isNewTask = taskId == null)
    )

    val uiState: StateFlow<TaskDetailUiState>

    init {
        if (taskId != null) {
            // Existing task — combine reactive data with local UI state
            uiState = combine(
                repository.getTaskById(taskId),
                repository.getChildTasks(taskId),
                repository.getCommentsForTask(taskId),
                repository.getRepeatingTaskForTask(taskId),
                _localState
            ) { task, children, comments, repeatingTask, local ->
                TaskDetailUiState(
                    task = task,
                    children = children,
                    comments = comments,
                    breadcrumbs = local.breadcrumbs,
                    repeatingTask = repeatingTask,
                    isEditing = local.isEditing,
                    isNewTask = false,
                    isLoading = false
                )
            }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), TaskDetailUiState())

            // Load breadcrumbs once
            viewModelScope.launch {
                val crumbs = repository.getBreadcrumbs(taskId)
                _localState.value = _localState.value.copy(breadcrumbs = crumbs)
            }
        } else {
            // New task
            _editState.value = EditState(parentId = parentIdArg)
            val newTaskState = MutableStateFlow(
                TaskDetailUiState(
                    isNewTask = true,
                    isEditing = true,
                    isLoading = false
                )
            )
            uiState = newTaskState

            // Load parent breadcrumbs for new task
            if (parentIdArg != null) {
                viewModelScope.launch {
                    val crumbs = repository.getBreadcrumbs(parentIdArg)
                    newTaskState.value = newTaskState.value.copy(breadcrumbs = crumbs)
                }
            }
        }
    }

    fun startEditing() {
        val task = uiState.value.task ?: return
        val repeating = uiState.value.repeatingTask
        _editState.value = EditState(
            title = task.title,
            description = task.description,
            status = task.status,
            priority = task.priority,
            dueDate = task.dueDate,
            parentId = task.parentId,
            repeatIntervalDays = repeating?.intervalDays,
            repeatStartDate = repeating?.startDate
        )
        _localState.value = _localState.value.copy(isEditing = true)
    }

    fun cancelEditing() {
        _localState.value = _localState.value.copy(isEditing = false)
    }

    fun updateTitle(title: String) {
        _editState.value = _editState.value.copy(title = title)
    }

    fun updateDescription(description: String) {
        _editState.value = _editState.value.copy(description = description)
    }

    fun updateStatus(status: TaskStatus) {
        _editState.value = _editState.value.copy(status = status)
    }

    fun updatePriority(priority: Int) {
        _editState.value = _editState.value.copy(priority = priority)
    }

    fun updateDueDate(dueDate: Long?) {
        _editState.value = _editState.value.copy(dueDate = dueDate)
    }

    fun updateParentId(parentId: String?) {
        _editState.value = _editState.value.copy(parentId = parentId)
    }

    fun updateRepeatIntervalDays(days: Int?) {
        _editState.value = _editState.value.copy(repeatIntervalDays = days)
    }

    fun updateRepeatStartDate(startDate: Long?) {
        _editState.value = _editState.value.copy(repeatStartDate = startDate)
    }

    fun save(onSaved: (String) -> Unit) {
        val edit = _editState.value
        if (edit.title.isBlank()) return

        viewModelScope.launch {
            if (uiState.value.isNewTask) {
                val task = repository.createTask(
                    title = edit.title,
                    description = edit.description,
                    parentId = edit.parentId,
                    priority = edit.priority,
                    dueDate = edit.dueDate
                )
                // Set repeating rule on the newly created task
                if (edit.repeatIntervalDays != null && edit.repeatIntervalDays > 0) {
                    val startDate = edit.repeatStartDate ?: System.currentTimeMillis()
                    repository.setRepeatingTask(task.id, edit.repeatIntervalDays, startDate)
                }
                onSaved(task.id)
            } else {
                val existing = uiState.value.task ?: return@launch

                // Cannot close a task if any children are still open
                if (edit.status == TaskStatus.CLOSED && existing.status != TaskStatus.CLOSED) {
                    val openChildren = uiState.value.children.filter {
                        it.status != TaskStatus.CLOSED
                    }
                    if (openChildren.isNotEmpty()) {
                        _errorMessage.value =
                            "Close all sub-tasks before closing this task " +
                            "(${openChildren.size} still open)"
                        return@launch
                    }
                }

                val updated = existing.copy(
                    title = edit.title,
                    description = edit.description,
                    status = edit.status,
                    priority = edit.priority,
                    dueDate = edit.dueDate,
                    parentId = edit.parentId
                )
                repository.updateTask(updated)

                // Update repeating rule
                val currentRepeating = uiState.value.repeatingTask
                if (edit.repeatIntervalDays != null && edit.repeatIntervalDays > 0) {
                    val startDate = edit.repeatStartDate
                        ?: currentRepeating?.startDate
                        ?: System.currentTimeMillis()
                    repository.setRepeatingTask(existing.id, edit.repeatIntervalDays, startDate)
                } else if (currentRepeating != null) {
                    repository.removeRepeatingTask(existing.id)
                }

                _localState.value = _localState.value.copy(isEditing = false)

                // Refresh breadcrumbs if parent changed
                if (existing.parentId != edit.parentId) {
                    val crumbs = repository.getBreadcrumbs(existing.id)
                    _localState.value = _localState.value.copy(breadcrumbs = crumbs)
                }
            }
        }
    }

    suspend fun getAllTasksForPicker(): List<Task> {
        return repository.getAllTasks()
    }

    suspend fun getDescendantIds(rootId: String): Set<String> {
        val allTasks = repository.getAllTasks()
        val childrenMap = allTasks.groupBy { it.parentId }
        val descendants = mutableSetOf<String>()
        fun collect(id: String) {
            childrenMap[id]?.forEach { child ->
                descendants.add(child.id)
                collect(child.id)
            }
        }
        collect(rootId)
        return descendants
    }

    fun addComment(text: String) {
        val id = taskId ?: return
        if (text.isBlank()) return
        viewModelScope.launch {
            repository.addComment(id, text)
        }
    }

    fun deleteComment(comment: Comment) {
        viewModelScope.launch {
            repository.deleteComment(comment)
        }
    }

    private data class LocalState(
        val isEditing: Boolean = false,
        val isNewTask: Boolean = false,
        val breadcrumbs: List<Task> = emptyList()
    )
}
