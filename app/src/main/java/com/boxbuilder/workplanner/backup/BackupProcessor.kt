package com.boxbuilder.workplanner.backup

import com.boxbuilder.workplanner.data.dao.CommentDao
import com.boxbuilder.workplanner.data.dao.TaskDao
import com.boxbuilder.workplanner.data.entity.CommentEntity
import com.boxbuilder.workplanner.data.entity.TaskEntity
import com.boxbuilder.workplanner.generic.kvstore.EntityRegistration
import com.boxbuilder.workplanner.generic.kvstore.IndexConfig
import com.boxbuilder.workplanner.generic.kvstore.KVStore
import com.boxbuilder.workplanner.generic.kvstore.PrimaryKeyConfig

class BackupProcessor(
    private val taskDao: TaskDao,
    private val commentDao: CommentDao,
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
    }

    suspend fun performBackup() {
        val tasks = taskDao.getAllTasks()
        val comments = commentDao.getAllComments()
        kvStore.saveAll("tasks", tasks)
        kvStore.saveAll("comments", comments)
    }

    suspend fun performRestore(): Boolean {
        if (!kvStore.exists("tasks")) return false

        val tasks = kvStore.getAll<TaskEntity>("tasks")
        val comments = kvStore.getAll<CommentEntity>("comments")

        // Delete tasks first — CASCADE clears comments
        taskDao.deleteAllTasks()
        taskDao.insertTasks(tasks)
        commentDao.insertComments(comments)

        return true
    }

    suspend fun hasRemoteBackup(): Boolean {
        return kvStore.exists("tasks")
    }
}
