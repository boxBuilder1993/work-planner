package com.boxbuilder.workplanner.data.room

import androidx.room.Database
import androidx.room.RoomDatabase
import com.boxbuilder.workplanner.data.entity.CommentEntity
import com.boxbuilder.workplanner.data.entity.TaskEntity

@Database(
    entities = [TaskEntity::class, CommentEntity::class],
    version = 1,
    exportSchema = true
)
abstract class WorkPlannerDatabase : RoomDatabase() {
    abstract fun roomTaskDao(): RoomTaskDao
    abstract fun roomCommentDao(): RoomCommentDao
}
