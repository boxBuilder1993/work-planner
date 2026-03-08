package com.boxbuilder.workplanner.backup

import android.content.Context
import android.util.Log
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.boxbuilder.workplanner.data.dao.RepeatingTaskDao
import com.boxbuilder.workplanner.data.dao.TaskDao
import com.boxbuilder.workplanner.data.entity.TaskEntity
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.UUID
import java.util.concurrent.TimeUnit

@HiltWorker
class RecurringTaskWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val taskDao: TaskDao,
    private val repeatingTaskDao: RepeatingTaskDao
) : CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result {
        return try {
            val repeatingTasks = repeatingTaskDao.getAll()
            val now = System.currentTimeMillis()

            for (rule in repeatingTasks) {
                // 1. Load template task
                val template = taskDao.getTaskByIdOnce(rule.taskId) ?: continue

                // 2. If template has a parent, check parent is not CLOSED
                if (template.parentId != null) {
                    val parent = taskDao.getTaskByIdOnce(template.parentId) ?: continue
                    if (parent.status == "CLOSED") continue
                }

                // 3. Compute next scheduled date anchored to startDate
                val intervalMs = rule.intervalDays.toLong() * 86_400_000L
                if (intervalMs <= 0) continue

                val nextScheduledDate = if (rule.lastCreatedAt == null) {
                    rule.startDate
                } else {
                    val elapsed = rule.lastCreatedAt - rule.startDate
                    val periods = (elapsed / intervalMs) + 1
                    rule.startDate + periods * intervalMs
                }

                // 4. Skip if not yet time
                if (now < nextScheduledDate) continue

                // 5. Create new task as sibling of template
                val sdf = java.text.SimpleDateFormat("MMM d, yyyy", java.util.Locale.getDefault())
                val datePrefix = sdf.format(java.util.Date(nextScheduledDate))
                val newTask = TaskEntity(
                    id = UUID.randomUUID().toString(),
                    parentId = template.parentId,
                    title = "$datePrefix - ${template.title}",
                    description = template.description,
                    status = "PENDING",
                    priority = template.priority,
                    dueDate = null,
                    taskDate = nextScheduledDate,
                    createdAt = now,
                    updatedAt = now
                )
                taskDao.insertTask(newTask)

                // 6. Update lastCreatedAt
                repeatingTaskDao.update(
                    rule.copy(
                        lastCreatedAt = now,
                        updatedAt = now
                    )
                )

                Log.d(TAG, "Created recurring task '${template.title}' (every ${rule.intervalDays} days), taskDate=${nextScheduledDate}")
            }

            Log.d(TAG, "Recurring task processing completed")
            Result.success()
        } catch (e: Exception) {
            Log.e(TAG, "Recurring task processing failed", e)
            Result.retry()
        }
    }

    companion object {
        private const val TAG = "RecurringTaskWorker"
        private const val WORK_NAME = "workplanner_recurring"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<RecurringTaskWorker>(1, TimeUnit.HOURS)
                .build()

            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(WORK_NAME, ExistingPeriodicWorkPolicy.KEEP, request)
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
        }
    }
}
