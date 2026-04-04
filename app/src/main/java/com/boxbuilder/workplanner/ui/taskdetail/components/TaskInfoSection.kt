package com.boxbuilder.workplanner.ui.taskdetail.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.boxbuilder.workplanner.data.model.RepeatingTask
import com.boxbuilder.workplanner.data.model.Task
import com.boxbuilder.workplanner.data.model.TaskStatus
import com.boxbuilder.workplanner.ui.taskdetail.EditState

@Composable
fun TaskInfoViewMode(
    task: Task,
    repeatingTask: RepeatingTask?,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Text(
            text = task.title,
            style = MaterialTheme.typography.headlineSmall
        )
        if (task.description.isNotBlank()) {
            Text(
                text = task.description,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        Row(
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            StatusChip(task.status)
            PriorityChip(task.priority)
            if (task.dueDate != null) {
                Text(
                    text = "Due: ${formatDate(task.dueDate)}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
        if (task.taskDate != null) {
            Text(
                text = "Task date: ${formatDate(task.taskDate)}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        if (task.aiEnabled) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val algoLabel = when (task.props["algorithm"]?.toString()) {
                    "decompose_and_delegate" -> "AI: D&D v1"
                    "decompose_and_delegate_v2" -> "AI: D&D v2"
                    else -> "AI: Simple"
                }
                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.tertiaryContainer
                ) {
                    Text(
                        text = algoLabel,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onTertiaryContainer,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                    )
                }
                val aiStatus = task.props["aiStatus"]?.toString()
                if (aiStatus != null) {
                    Surface(
                        shape = RoundedCornerShape(16.dp),
                        color = MaterialTheme.colorScheme.surfaceVariant
                    ) {
                        Text(
                            text = aiStatus.replace("_", " "),
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                        )
                    }
                }
            }
        }
        if (repeatingTask != null) {
            Surface(
                shape = RoundedCornerShape(16.dp),
                color = MaterialTheme.colorScheme.secondaryContainer
            ) {
                Text(
                    text = "Repeats every ${repeatingTask.intervalDays} day${if (repeatingTask.intervalDays != 1) "s" else ""} · starts ${formatDate(repeatingTask.startDate)}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskInfoEditMode(
    editState: EditState,
    isNewTask: Boolean,
    onTitleChange: (String) -> Unit,
    onDescriptionChange: (String) -> Unit,
    onStatusChange: (TaskStatus) -> Unit,
    onPriorityChange: (Int) -> Unit,
    onDueDateChange: (Long?) -> Unit,
    onRepeatIntervalChange: (Int?) -> Unit,
    onRepeatStartDateChange: (Long?) -> Unit,
    onAiEnabledChange: (Boolean) -> Unit,
    onAiAlgorithmChange: (String) -> Unit,
    onChangeParentClick: () -> Unit,
    parentName: String?,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        OutlinedTextField(
            value = editState.title,
            onValueChange = onTitleChange,
            label = { Text("Title") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        OutlinedTextField(
            value = editState.description,
            onValueChange = onDescriptionChange,
            label = { Text("Description") },
            modifier = Modifier.fillMaxWidth(),
            minLines = 3
        )

        // Status dropdown (not editable on create)
        if (!isNewTask) {
            StatusDropdown(
                status = editState.status,
                onStatusChange = onStatusChange
            )
        }

        // Priority dropdown
        PriorityDropdown(
            priority = editState.priority,
            onPriorityChange = onPriorityChange
        )

        // Due date
        DueDateField(
            dueDate = editState.dueDate,
            onDueDateChange = onDueDateChange
        )

        // Repeat interval (days)
        RepeatIntervalField(
            intervalDays = editState.repeatIntervalDays,
            onIntervalChange = onRepeatIntervalChange
        )

        // Repeat start date (only shown when repeat is set)
        if (editState.repeatIntervalDays != null && editState.repeatIntervalDays > 0) {
            RepeatStartDateField(
                startDate = editState.repeatStartDate,
                onStartDateChange = onRepeatStartDateChange
            )
        }

        // AI Enabled toggle
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("AI Enabled", style = MaterialTheme.typography.bodyLarge)
            androidx.compose.material3.Switch(
                checked = editState.aiEnabled,
                onCheckedChange = onAiEnabledChange
            )
        }

        // AI Algorithm picker (only when AI is enabled)
        if (editState.aiEnabled) {
            var algoExpanded by remember { mutableStateOf(false) }
            val algoOptions = listOf("simple_answer" to "Simple Answer", "decompose_and_delegate" to "D&D (v1)", "decompose_and_delegate_v2" to "D&D v2", "sdlc" to "SDLC")
            val currentLabel = algoOptions.firstOrNull { it.first == editState.aiAlgorithm }?.second ?: "Simple Answer"
            ExposedDropdownMenuBox(
                expanded = algoExpanded,
                onExpandedChange = { algoExpanded = it }
            ) {
                OutlinedTextField(
                    value = currentLabel,
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("AI Algorithm") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = algoExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable)
                )
                ExposedDropdownMenu(
                    expanded = algoExpanded,
                    onDismissRequest = { algoExpanded = false }
                ) {
                    algoOptions.forEach { (value, label) ->
                        DropdownMenuItem(
                            text = { Text(label) },
                            onClick = {
                                onAiAlgorithmChange(value)
                                algoExpanded = false
                            }
                        )
                    }
                }
            }
        }

        // Parent picker (not on new tasks — parent is set by navigation)
        if (!isNewTask) {
            OutlinedTextField(
                value = parentName ?: "None (root-level theme)",
                onValueChange = {},
                readOnly = true,
                label = { Text("Parent") },
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable(onClick = onChangeParentClick),
                enabled = false
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun StatusDropdown(
    status: TaskStatus,
    onStatusChange: (TaskStatus) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = status.name,
            onValueChange = {},
            readOnly = true,
            label = { Text("Status") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(MenuAnchorType.PrimaryNotEditable)
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            TaskStatus.entries.forEach { s ->
                DropdownMenuItem(
                    text = { Text(s.name) },
                    onClick = { onStatusChange(s); expanded = false }
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PriorityDropdown(
    priority: Int,
    onPriorityChange: (Int) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = priority.toString(),
            onValueChange = {},
            readOnly = true,
            label = { Text("Priority") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(MenuAnchorType.PrimaryNotEditable)
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            (1..5).forEach { p ->
                DropdownMenuItem(
                    text = { Text("$p") },
                    onClick = { onPriorityChange(p); expanded = false }
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DueDateField(
    dueDate: Long?,
    onDueDateChange: (Long?) -> Unit
) {
    var showDatePicker by remember { mutableStateOf(false) }

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        OutlinedTextField(
            value = dueDate?.let { formatDate(it) } ?: "",
            onValueChange = {},
            readOnly = true,
            label = { Text("Due date") },
            placeholder = { Text("No due date") },
            modifier = Modifier
                .weight(1f)
                .clickable { showDatePicker = true },
            trailingIcon = {
                Row {
                    IconButton(onClick = { showDatePicker = true }) {
                        Icon(Icons.Default.DateRange, contentDescription = "Pick date")
                    }
                    if (dueDate != null) {
                        IconButton(onClick = { onDueDateChange(null) }) {
                            Icon(Icons.Default.Clear, contentDescription = "Clear date")
                        }
                    }
                }
            },
            enabled = false
        )
    }

    if (showDatePicker) {
        val datePickerState = rememberDatePickerState(initialSelectedDateMillis = dueDate)
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    onDueDateChange(datePickerState.selectedDateMillis)
                    showDatePicker = false
                }) { Text("OK") }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) { Text("Cancel") }
            }
        ) {
            DatePicker(state = datePickerState)
        }
    }
}

@Composable
private fun StatusChip(status: TaskStatus) {
    val color = when (status) {
        TaskStatus.PENDING -> MaterialTheme.colorScheme.primary
        TaskStatus.CLOSED -> Color.Gray
    }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Surface(
            shape = RoundedCornerShape(50),
            color = color,
            modifier = Modifier.size(10.dp)
        ) {}
        Text(
            text = " ${status.name}",
            style = MaterialTheme.typography.bodyMedium
        )
    }
}

@Composable
private fun PriorityChip(priority: Int) {
    val color = when (priority) {
        1 -> Color(0xFFE53935)
        2 -> Color(0xFFF57C00)
        3 -> Color(0xFFFDD835)
        4 -> Color(0xFF43A047)
        5 -> Color(0xFF1E88E5)
        else -> Color.Gray
    }
    Surface(
        shape = RoundedCornerShape(4.dp),
        color = color,
        modifier = Modifier.size(24.dp)
    ) {
        Text(
            text = priority.toString(),
            style = MaterialTheme.typography.labelSmall,
            color = Color.White,
            modifier = Modifier.padding(4.dp)
        )
    }
}

@Composable
private fun RepeatIntervalField(
    intervalDays: Int?,
    onIntervalChange: (Int?) -> Unit
) {
    OutlinedTextField(
        value = intervalDays?.toString() ?: "",
        onValueChange = { text ->
            if (text.isEmpty()) {
                onIntervalChange(null)
            } else {
                text.toIntOrNull()?.let { if (it >= 0) onIntervalChange(it) }
            }
        },
        label = { Text("Repeat every (days)") },
        placeholder = { Text("Off") },
        modifier = Modifier.fillMaxWidth(),
        singleLine = true,
        trailingIcon = {
            if (intervalDays != null) {
                IconButton(onClick = { onIntervalChange(null) }) {
                    Icon(Icons.Default.Clear, contentDescription = "Clear repeat")
                }
            }
        }
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RepeatStartDateField(
    startDate: Long?,
    onStartDateChange: (Long?) -> Unit
) {
    var showDatePicker by remember { mutableStateOf(false) }

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        OutlinedTextField(
            value = startDate?.let { formatDate(it) } ?: "",
            onValueChange = {},
            readOnly = true,
            label = { Text("Repeat start date") },
            placeholder = { Text("Now") },
            modifier = Modifier
                .weight(1f)
                .clickable { showDatePicker = true },
            trailingIcon = {
                Row {
                    IconButton(onClick = { showDatePicker = true }) {
                        Icon(Icons.Default.DateRange, contentDescription = "Pick start date")
                    }
                    if (startDate != null) {
                        IconButton(onClick = { onStartDateChange(null) }) {
                            Icon(Icons.Default.Clear, contentDescription = "Clear start date")
                        }
                    }
                }
            },
            enabled = false
        )
    }

    if (showDatePicker) {
        val datePickerState = rememberDatePickerState(initialSelectedDateMillis = startDate)
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    onStartDateChange(datePickerState.selectedDateMillis)
                    showDatePicker = false
                }) { Text("OK") }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) { Text("Cancel") }
            }
        ) {
            DatePicker(state = datePickerState)
        }
    }
}

private fun formatDate(millis: Long): String {
    val sdf = java.text.SimpleDateFormat("MMM d, yyyy", java.util.Locale.getDefault())
    return sdf.format(java.util.Date(millis))
}
