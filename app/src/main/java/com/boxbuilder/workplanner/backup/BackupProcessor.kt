package com.boxbuilder.workplanner.backup

import com.boxbuilder.workplanner.data.dao.CommentDao
import com.boxbuilder.workplanner.data.dao.RepeatingTaskDao
import com.boxbuilder.workplanner.data.dao.TaskDao
import com.boxbuilder.workplanner.data.entity.CommentEntity
import com.boxbuilder.workplanner.data.entity.RepeatingTaskEntity
import com.boxbuilder.workplanner.data.entity.TaskEntity
import com.boxbuilder.workplanner.generic.kvstore.EntityRegistration
import com.boxbuilder.workplanner.generic.kvstore.IndexConfig
import com.boxbuilder.workplanner.generic.kvstore.KVStore
import com.boxbuilder.workplanner.generic.kvstore.PrimaryKeyConfig

class BackupProcessor(
    private val taskDao: TaskDao,
    private val commentDao: CommentDao,
    private val repeatingTaskDao: RepeatingTaskDao,
    private val kvStore: KVStore
) {
    init {
        kvStore.registerEntity("tasks", EntityRegistration(
            primaryKey = PrimaryKeyConfig<TaskEntity>(
                componentNames = listOf("id"),
                extractor = { mapOf("id" to it.id) }
            ),
            indexes = listOf(
                IndexConfig("parentId_index", listOf("parentId")) {
                    mapOf("parentId" to (it.parentId ?: "null"))
                },
                IndexConfig("status_index", listOf("status")) {
                    mapOf("status" to it.status)
                }
            ),
            serializer = TaskEntity.serializer()
        ))

        kvStore.registerEntity("comments", EntityRegistration(
            primaryKey = PrimaryKeyConfig<CommentEntity>(
                componentNames = listOf("id"),
                extractor = { mapOf("id" to it.id) }
            ),
            indexes = listOf(
                IndexConfig("taskId_index", listOf("taskId")) {
                    mapOf("taskId" to it.taskId)
                }
            ),
            serializer = CommentEntity.serializer()
        ))

        kvStore.registerEntity("repeating_tasks", EntityRegistration(
            primaryKey = PrimaryKeyConfig<RepeatingTaskEntity>(
                componentNames = listOf("id"),
                extractor = { mapOf("id" to it.id) }
            ),
            indexes = listOf(
                IndexConfig("taskId_index", listOf("taskId")) {
                    mapOf("taskId" to it.taskId)
                }
            ),
            serializer = RepeatingTaskEntity.serializer()
        ))
    }

    suspend fun performBackup() {
        val tasks = taskDao.getAllTasks()
        val comments = commentDao.getAllComments()
        val repeatingTasks = repeatingTaskDao.getAll()
        kvStore.saveAll("tasks", tasks)
        kvStore.saveAll("comments", comments)
        kvStore.saveAll("repeating_tasks", repeatingTasks)
    }

    suspend fun performRestore(): Boolean {
        if (!kvStore.exists("tasks")) return false

        val tasks = kvStore.getAll<TaskEntity>("tasks")
        val comments = kvStore.getAll<CommentEntity>("comments")

        // Repeating tasks — backward-compatible (old backups won't have this)
        val repeatingTasks = if (kvStore.exists("repeating_tasks")) {
            kvStore.getAll<RepeatingTaskEntity>("repeating_tasks")
        } else {
            emptyList()
        }

        // Delete tasks first — CASCADE clears comments and repeating tasks
        taskDao.deleteAllTasks()
        taskDao.insertTasks(tasks)
        commentDao.insertComments(comments)
        if (repeatingTasks.isNotEmpty()) {
            repeatingTaskDao.insertAll(repeatingTasks)
        }

        return true
    }

    suspend fun hasRemoteBackup(): Boolean {
        return kvStore.exists("tasks")
    }
}
