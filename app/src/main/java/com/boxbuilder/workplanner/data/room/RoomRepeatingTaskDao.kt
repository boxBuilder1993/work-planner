package com.boxbuilder.workplanner.data.room

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import com.boxbuilder.workplanner.data.dao.RepeatingTaskDao
import com.boxbuilder.workplanner.data.entity.RepeatingTaskEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface RoomRepeatingTaskDao : RepeatingTaskDao {

    // ── Reactive queries ─────────────────────────────────────

    @Query("SELECT * FROM repeating_tasks WHERE taskId = :taskId")
    override fun getByTaskId(taskId: String): Flow<RepeatingTaskEntity?>

    // ── One-shot queries ─────────────────────────────────────

    @Query("SELECT * FROM repeating_tasks")
    override suspend fun getAll(): List<RepeatingTaskEntity>

    // ── Mutations ────────────────────────────────────────────

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    override suspend fun insert(entity: RepeatingTaskEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    override suspend fun insertAll(entities: List<RepeatingTaskEntity>)

    @Update
    override suspend fun update(entity: RepeatingTaskEntity)

    @Query("DELETE FROM repeating_tasks WHERE taskId = :taskId")
    override suspend fun deleteByTaskId(taskId: String)

    @Query("DELETE FROM repeating_tasks")
    override suspend fun deleteAll()
}
