package com.boxbuilder.workplanner.data.room

import androidx.room.Database
import androidx.room.RoomDatabase
import com.boxbuilder.workplanner.data.entity.CommentEntity
import com.boxbuilder.workplanner.data.entity.RepeatingTaskEntity
import com.boxbuilder.workplanner.data.entity.TaskEntity

@Database(
    entities = [TaskEntity::class, CommentEntity::class, RepeatingTaskEntity::class],
    version = 3,
    exportSchema = true
)
abstract class WorkPlannerDatabase : RoomDatabase() {
    abstract fun roomTaskDao(): RoomTaskDao
    abstract fun roomCommentDao(): RoomCommentDao
    abstract fun roomRepeatingTaskDao(): RoomRepeatingTaskDao
}
