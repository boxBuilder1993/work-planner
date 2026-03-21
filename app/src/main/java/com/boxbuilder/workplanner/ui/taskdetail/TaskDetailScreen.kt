package com.boxbuilder.workplanner.ui.taskdetail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.boxbuilder.workplanner.data.model.Task
import com.boxbuilder.workplanner.data.model.TaskStatus
import com.boxbuilder.workplanner.ui.common.components.LoadingIndicator
import com.boxbuilder.workplanner.ui.taskdetail.components.BreadcrumbBar
import com.boxbuilder.workplanner.ui.taskdetail.components.CommentSection
import com.boxbuilder.workplanner.ui.taskdetail.components.ParentPickerDialog
import com.boxbuilder.workplanner.ui.taskdetail.components.TaskInfoEditMode
import com.boxbuilder.workplanner.ui.taskdetail.components.TaskInfoViewMode
import com.boxbuilder.workplanner.ui.tasklist.components.TaskCard
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskDetailScreen(
    onBack: () -> Unit,
    onTaskClick: (String) -> Unit,
    onNewChild: (String) -> Unit,
    onNavigateToTask: (String) -> Unit,
    viewModel: TaskDetailViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val editState by viewModel.editState.collectAsStateWithLifecycle()
    val errorMessage by viewModel.errorMessage.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val snackbarHostState = remember { SnackbarHostState() }

    // Show error message as snackbar
    LaunchedEffect(errorMessage) {
        errorMessage?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.clearError()
        }
    }

    // Parent picker state
    var showParentPicker by remember { mutableStateOf(false) }
    var allTasks by remember { mutableStateOf(emptyList<Task>()) }
    var descendantIds by remember { mutableStateOf(emptySet<String>()) }

    // Resolve parent name from editState.parentId (try allTasks first, fall back to breadcrumbs)
    val parentName = remember(editState.parentId, allTasks, uiState.breadcrumbs) {
        editState.parentId?.let { pid ->
            allTasks.find { it.id == pid }?.title
                ?: uiState.breadcrumbs.find { it.id == pid }?.title
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            TopAppBar(
                title = {},
                navigationIcon = {
                    IconButton(onClick = {
                        if (uiState.isEditing && !uiState.isNewTask) {
                            viewModel.cancelEditing()
                        } else {
                            onBack()
                        }
                    }) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    if (uiState.isEditing) {
                        TextButton(onClick = {
                            if (uiState.isNewTask) onBack()
                            else viewModel.cancelEditing()
                        }) { Text("Cancel") }
                        TextButton(onClick = {
                            viewModel.save { newId ->
                                if (uiState.isNewTask) {
                                    onNavigateToTask(newId)
                                }
                            }
                        }) { Text("Save") }
                    } else if (uiState.task != null) {
                        IconButton(onClick = { viewModel.startEditing() }) {
                            Icon(Icons.Default.Edit, contentDescription = "Edit")
                        }
                    }
                }
            )
        }
    ) { padding ->
        if (uiState.isLoading) {
            LoadingIndicator(modifier = Modifier.padding(padding))
            return@Scaffold
        }

        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(bottom = 32.dp)
        ) {
            // Breadcrumbs
            if (uiState.breadcrumbs.isNotEmpty()) {
                item {
                    BreadcrumbBar(
                        breadcrumbs = uiState.breadcrumbs,
                        onRootClick = onBack,
                        onCrumbClick = onNavigateToTask
                    )
                    HorizontalDivider()
                }
            }

            // Task info
            item {
                if (uiState.isEditing) {
                    TaskInfoEditMode(
                        editState = editState,
                        isNewTask = uiState.isNewTask,
                        onTitleChange = viewModel::updateTitle,
                        onDescriptionChange = viewModel::updateDescription,
                        onStatusChange = viewModel::updateStatus,
                        onPriorityChange = viewModel::updatePriority,
                        onDueDateChange = viewModel::updateDueDate,
                        onRepeatIntervalChange = viewModel::updateRepeatIntervalDays,
                        onRepeatStartDateChange = viewModel::updateRepeatStartDate,
                        onAiEnabledChange = viewModel::updateAiEnabled,
                        onAiAlgorithmChange = viewModel::updateAiAlgorithm,
                        onChangeParentClick = {
                            scope.launch {
                                allTasks = viewModel.getAllTasksForPicker()
                                uiState.task?.let { task ->
                                    descendantIds = viewModel.getDescendantIds(task.id)
                                }
                                showParentPicker = true
                            }
                        },
                        parentName = parentName,
                        modifier = Modifier.padding(top = 16.dp)
                    )
                } else {
                    uiState.task?.let { task ->
                        TaskInfoViewMode(
                            task = task,
                            repeatingTask = uiState.repeatingTask,
                            modifier = Modifier.padding(top = 16.dp)
                        )
                    }
                }
            }

            // Sub-tasks section (only for existing tasks)
            if (!uiState.isNewTask) {
                item {
                    Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 16.dp)) {
                        Text(
                            text = "Sub-tasks (${uiState.children.size})",
                            style = MaterialTheme.typography.titleSmall
                        )
                    }
                }

                items(uiState.children, key = { it.id }) { child ->
                    TaskCard(
                        task = child,
                        onClick = { onTaskClick(child.id) },
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                    )
                }

                // Hide "+ Add Child" for closed tasks
                if (uiState.task?.status != TaskStatus.CLOSED) {
                    item {
                        Button(
                            onClick = {
                                uiState.task?.let { onNewChild(it.id) }
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 16.dp, vertical = 8.dp)
                        ) {
                            Text("+ Add Child")
                        }
                    }
                }

                // Comments section
                item {
                    HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                    CommentSection(
                        comments = uiState.comments,
                        onAddComment = viewModel::addComment,
                        onDeleteComment = viewModel::deleteComment,
                        onApproveProposal = viewModel::approveProposal,
                        onDenyProposal = viewModel::denyProposal,
                        modifier = Modifier.padding(horizontal = 16.dp)
                    )
                }
            }
        }

        // Parent picker dialog
        if (showParentPicker) {
            ParentPickerDialog(
                tasks = allTasks,
                currentParentId = editState.parentId,
                excludeTaskId = uiState.task?.id,
                excludeDescendantIds = descendantIds,
                onParentSelected = { newParentId ->
                    viewModel.updateParentId(newParentId)
                    showParentPicker = false
                },
                onDismiss = { showParentPicker = false }
            )
        }
    }
}
