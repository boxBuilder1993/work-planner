package com.boxbuilder.workplanner.ui.tasklist

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.boxbuilder.workplanner.data.model.Task
import com.boxbuilder.workplanner.ui.tasklist.components.EmptyState
import com.boxbuilder.workplanner.ui.tasklist.components.SearchFilterBar
import com.boxbuilder.workplanner.ui.tasklist.components.TaskCard

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskListScreen(
    onTaskClick: (String) -> Unit,
    onNewTask: (parentId: String?) -> Unit,
    onSettingsClick: () -> Unit,
    viewModel: TaskListViewModel = hiltViewModel()
) {
    val selectedTab by viewModel.selectedTab.collectAsStateWithLifecycle()
    val themes by viewModel.themes.collectAsStateWithLifecycle()
    val actionableItems by viewModel.actionableItems.collectAsStateWithLifecycle()
    val searchQuery by viewModel.searchQuery.collectAsStateWithLifecycle()
    val searchFilters by viewModel.searchFilters.collectAsStateWithLifecycle()
    val searchResults by viewModel.searchResults.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("WorkPlanner") },
                actions = {
                    IconButton(onClick = onSettingsClick) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings")
                    }
                }
            )
        },
        floatingActionButton = {
            if (selectedTab == Tab.THEMES) {
                FloatingActionButton(onClick = { onNewTask(null) }) {
                    Icon(Icons.Default.Add, contentDescription = "New theme")
                }
            }
        }
    ) { padding ->
        Column(modifier = Modifier.padding(padding)) {
            TabRow(selectedTabIndex = selectedTab.ordinal) {
                Tab(
                    selected = selectedTab == Tab.THEMES,
                    onClick = { viewModel.selectTab(Tab.THEMES) },
                    text = { Text("Themes") }
                )
                Tab(
                    selected = selectedTab == Tab.ACTIONABLE,
                    onClick = { viewModel.selectTab(Tab.ACTIONABLE) },
                    text = { Text("Actionable") }
                )
                Tab(
                    selected = selectedTab == Tab.SEARCH,
                    onClick = { viewModel.selectTab(Tab.SEARCH) },
                    text = { Text("Search") }
                )
            }

            when (selectedTab) {
                Tab.THEMES -> ThemesTab(
                    tasks = themes,
                    onTaskClick = onTaskClick
                )
                Tab.ACTIONABLE -> ActionableTab(
                    tasks = actionableItems,
                    viewModel = viewModel,
                    onTaskClick = onTaskClick
                )
                Tab.SEARCH -> SearchTab(
                    query = searchQuery,
                    filters = searchFilters,
                    results = searchResults,
                    viewModel = viewModel,
                    onQueryChange = viewModel::updateSearchQuery,
                    onFiltersChange = viewModel::updateSearchFilters,
                    onTaskClick = onTaskClick
                )
            }
        }
    }
}

@Composable
private fun ThemesTab(
    tasks: List<Task>,
    onTaskClick: (String) -> Unit
) {
    if (tasks.isEmpty()) {
        EmptyState(
            title = "No themes yet",
            subtitle = "Tap + to create your first theme"
        )
    } else {
        LazyColumn(
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(tasks, key = { it.id }) { task ->
                TaskCard(
                    task = task,
                    onClick = { onTaskClick(task.id) }
                )
            }
        }
    }
}

@Composable
private fun ActionableTab(
    tasks: List<Task>,
    viewModel: TaskListViewModel,
    onTaskClick: (String) -> Unit
) {
    if (tasks.isEmpty()) {
        EmptyState(
            title = "No actionable tasks",
            subtitle = "Actionable tasks are leaf-level tasks with no sub-tasks."
        )
    } else {
        LazyColumn(
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(tasks, key = { it.id }) { task ->
                var path by remember(task.id) { mutableStateOf<List<String>>(emptyList()) }
                LaunchedEffect(task.id) {
                    path = viewModel.getPathForTask(task)
                }
                TaskCard(
                    task = task,
                    path = path,
                    showPriority = true,
                    showDueDate = true,
                    onClick = { onTaskClick(task.id) }
                )
            }
        }
    }
}

@Composable
private fun SearchTab(
    query: String,
    filters: SearchFilters,
    results: List<Task>,
    viewModel: TaskListViewModel,
    onQueryChange: (String) -> Unit,
    onFiltersChange: (SearchFilters) -> Unit,
    onTaskClick: (String) -> Unit
) {
    Column(modifier = Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = query,
            onValueChange = onQueryChange,
            placeholder = { Text("Search tasks...") },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            singleLine = true
        )

        SearchFilterBar(
            filters = filters,
            onFiltersChange = onFiltersChange,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        if (query.isBlank()) {
            EmptyState(
                title = "Search across all tasks",
                subtitle = "by title or description"
            )
        } else if (results.isEmpty()) {
            EmptyState(
                title = "No tasks found",
                subtitle = "Try adjusting your filters"
            )
        } else {
            LazyColumn(
                contentPadding = PaddingValues(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(results, key = { it.id }) { task ->
                    var path by remember(task.id) { mutableStateOf<List<String>>(emptyList()) }
                    LaunchedEffect(task.id) {
                        path = viewModel.getPathForTask(task)
                    }
                    TaskCard(
                        task = task,
                        path = path,
                        showPriority = true,
                        showDueDate = true,
                        onClick = { onTaskClick(task.id) }
                    )
                }
            }
        }
    }
}
