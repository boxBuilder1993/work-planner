package com.boxbuilder.workplanner.data.api.dto

import com.boxbuilder.workplanner.data.model.Comment
import com.boxbuilder.workplanner.data.model.RepeatingTask
import com.boxbuilder.workplanner.data.model.Task
import com.boxbuilder.workplanner.data.model.TaskStatus
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

private val isoFormat: SimpleDateFormat
    get() = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }

fun String.parseIso(): Long = try {
    isoFormat.parse(this)?.time ?: 0L
} catch (_: Exception) {
    0L
}

fun Long.toIso(): String = isoFormat.format(this)

fun Long?.toIsoOrNull(): String? = this?.let { isoFormat.format(it) }

fun TaskDto.toDomain(): Task = Task(
    id = id,
    parentId = parentId,
    title = title,
    description = description,
    status = try { TaskStatus.valueOf(status) } catch (_: Exception) { TaskStatus.PENDING },
    priority = priority,
    dueDate = dueDate?.parseIso(),
    taskDate = taskDate?.parseIso(),
    plannedTime = plannedTime?.parseIso(),
    duration = duration,
    createdAt = createdAt.parseIso(),
    updatedAt = updatedAt.parseIso()
)

fun CommentDto.toDomain(): Comment = Comment(
    id = id,
    taskId = taskId,
    text = text,
    createdAt = createdAt.parseIso(),
    updatedAt = updatedAt.parseIso()
)

fun RepeatingTaskDto.toDomain(): RepeatingTask = RepeatingTask(
    id = id,
    taskId = taskId,
    intervalDays = repetitionProps["interval_days"]?.toIntOrNull() ?: 0,
    startDate = repetitionProps["start_date"]?.parseIso() ?: 0L,
    lastCreatedAt = repetitionProps["last_created_at"]?.parseIso(),
    createdAt = createdAt.parseIso(),
    updatedAt = updatedAt.parseIso()
)
