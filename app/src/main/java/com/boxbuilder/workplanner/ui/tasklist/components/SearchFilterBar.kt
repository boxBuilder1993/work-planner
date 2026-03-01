package com.boxbuilder.workplanner.ui.tasklist.components

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.boxbuilder.workplanner.ui.tasklist.DueDateFilter
import com.boxbuilder.workplanner.ui.tasklist.SearchFilters
import com.boxbuilder.workplanner.ui.tasklist.StatusFilter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SearchFilterBar(
    filters: SearchFilters,
    onFiltersChange: (SearchFilters) -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        // Status filter chip
        var showStatusMenu by remember { mutableStateOf(false) }
        ChipWithDropdown(
            label = "Status: ${filters.status.label}",
            selected = filters.status != StatusFilter.ALL,
            expanded = showStatusMenu,
            onExpandChange = { showStatusMenu = it },
            items = StatusFilter.entries,
            itemLabel = { it.label },
            onItemSelected = {
                onFiltersChange(filters.copy(status = it))
                showStatusMenu = false
            }
        )

        // Priority filter chip
        var showPriorityMenu by remember { mutableStateOf(false) }
        val priorityLabel = if (filters.minPriority == 1 && filters.maxPriority == 5) {
            "Priority: All"
        } else if (filters.minPriority == filters.maxPriority) {
            "Priority: ${filters.minPriority}"
        } else {
            "Priority: ${filters.minPriority}–${filters.maxPriority}"
        }
        ChipWithDropdown(
            label = priorityLabel,
            selected = filters.minPriority != 1 || filters.maxPriority != 5,
            expanded = showPriorityMenu,
            onExpandChange = { showPriorityMenu = it },
            items = listOf(
                "All" to (1 to 5),
                "1 (Urgent)" to (1 to 1),
                "1–2 (High)" to (1 to 2),
                "1–3 (High–Med)" to (1 to 3),
                "4–5 (Low)" to (4 to 5)
            ),
            itemLabel = { it.first },
            onItemSelected = { (_, range) ->
                onFiltersChange(filters.copy(minPriority = range.first, maxPriority = range.second))
                showPriorityMenu = false
            }
        )

        // Due date filter chip
        var showDueDateMenu by remember { mutableStateOf(false) }
        ChipWithDropdown(
            label = "Due: ${filters.dueDate.label}",
            selected = filters.dueDate != DueDateFilter.ANY,
            expanded = showDueDateMenu,
            onExpandChange = { showDueDateMenu = it },
            items = DueDateFilter.entries,
            itemLabel = { it.label },
            onItemSelected = {
                onFiltersChange(filters.copy(dueDate = it))
                showDueDateMenu = false
            }
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun <T> ChipWithDropdown(
    label: String,
    selected: Boolean,
    expanded: Boolean,
    onExpandChange: (Boolean) -> Unit,
    items: List<T>,
    itemLabel: (T) -> String,
    onItemSelected: (T) -> Unit
) {
    FilterChip(
        selected = selected,
        onClick = { onExpandChange(!expanded) },
        label = { Text(label) }
    )
    DropdownMenu(
        expanded = expanded,
        onDismissRequest = { onExpandChange(false) }
    ) {
        items.forEach { item ->
            DropdownMenuItem(
                text = { Text(itemLabel(item)) },
                onClick = { onItemSelected(item) }
            )
        }
    }
}

private val StatusFilter.label: String
    get() = when (this) {
        StatusFilter.ALL -> "All"
        StatusFilter.PENDING -> "Pending"
        StatusFilter.CLOSED -> "Closed"
    }

private val DueDateFilter.label: String
    get() = when (this) {
        DueDateFilter.ANY -> "Any"
        DueDateFilter.HAS_DUE_DATE -> "Has date"
        DueDateFilter.OVERDUE -> "Overdue"
        DueDateFilter.NO_DUE_DATE -> "No date"
    }
