package com.boxbuilder.workplanner.data.dao

import com.boxbuilder.workplanner.data.entity.RepeatingTaskEntity
import kotlinx.coroutines.flow.Flow

interface RepeatingTaskDao {

    // ── Reactive queries ─────────────────────────────────────

    fun getByTaskId(taskId: String): Flow<RepeatingTaskEntity?>

    // ── One-shot queries ─────────────────────────────────────

    suspend fun getAll(): List<RepeatingTaskEntity>

    // ── Mutations ────────────────────────────────────────────

    suspend fun insert(entity: RepeatingTaskEntity)

    suspend fun insertAll(entities: List<RepeatingTaskEntity>)

    suspend fun update(entity: RepeatingTaskEntity)

    suspend fun deleteByTaskId(taskId: String)

    suspend fun deleteAll()
}
