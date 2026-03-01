package com.boxbuilder.workplanner.ui.tasklist

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.boxbuilder.workplanner.data.TaskRepository
import com.boxbuilder.workplanner.data.model.Task
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

data class TaskWithPath(
    val task: Task,
    val path: List<String>
)

enum class Tab { THEMES, ACTIONABLE, SEARCH }

@OptIn(ExperimentalCoroutinesApi::class, FlowPreview::class)
@HiltViewModel
class TaskListViewModel @Inject constructor(
    private val repository: TaskRepository
) : ViewModel() {

    private val _selectedTab = MutableStateFlow(Tab.THEMES)
    val selectedTab: StateFlow<Tab> = _selectedTab.asStateFlow()

    val themes: StateFlow<List<Task>> = repository.getPendingRootTasks()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    val actionableItems: StateFlow<List<Task>> = repository.getLeafTasks()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    val searchResults: StateFlow<List<Task>> = _searchQuery
        .debounce(300)
        .flatMapLatest { query ->
            if (query.isBlank()) flowOf(emptyList())
            else repository.searchTasks(query)
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    // Cache for hierarchy paths used by Actionable and Search tabs
    private val _pathCache = mutableMapOf<String, List<String>>()

    fun selectTab(tab: Tab) {
        _selectedTab.value = tab
    }

    fun updateSearchQuery(query: String) {
        _searchQuery.value = query
    }

    suspend fun getPathForTask(task: Task): List<String> {
        _pathCache[task.id]?.let { return it }
        val breadcrumbs = repository.getBreadcrumbs(task.id)
        // Path is all ancestors except the task itself
        val path = breadcrumbs.dropLast(1).map { it.title }
        _pathCache[task.id] = path
        return path
    }
}
