package com.boxbuilder.workplanner.di

import android.content.Context
import androidx.room.Room
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.boxbuilder.workplanner.data.TaskRepository
import com.boxbuilder.workplanner.data.dao.CommentDao
import com.boxbuilder.workplanner.data.dao.RepeatingTaskDao
import com.boxbuilder.workplanner.data.dao.TaskDao
import com.boxbuilder.workplanner.data.room.WorkPlannerDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS repeating_tasks (
                id TEXT NOT NULL PRIMARY KEY,
                taskId TEXT NOT NULL,
                intervalDays INTEGER NOT NULL,
                startDate INTEGER NOT NULL,
                lastCreatedAt INTEGER,
                createdAt INTEGER NOT NULL,
                updatedAt INTEGER NOT NULL,
                FOREIGN KEY (taskId) REFERENCES tasks(id) ON DELETE CASCADE
            )
            """.trimIndent()
        )
        db.execSQL("CREATE INDEX IF NOT EXISTS index_repeating_tasks_taskId ON repeating_tasks(taskId)")
        db.execSQL("ALTER TABLE tasks ADD COLUMN taskDate INTEGER")
    }
}

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): WorkPlannerDatabase {
        return Room.databaseBuilder(
            context,
            WorkPlannerDatabase::class.java,
            "workplanner.db"
        )
            .addMigrations(MIGRATION_1_2)
            .build()
    }

    @Provides
    fun provideTaskDao(db: WorkPlannerDatabase): TaskDao = db.roomTaskDao()

    @Provides
    fun provideCommentDao(db: WorkPlannerDatabase): CommentDao = db.roomCommentDao()

    @Provides
    fun provideRepeatingTaskDao(db: WorkPlannerDatabase): RepeatingTaskDao = db.roomRepeatingTaskDao()

    @Provides
    @Singleton
    fun provideTaskRepository(
        taskDao: TaskDao,
        commentDao: CommentDao,
        repeatingTaskDao: RepeatingTaskDao
    ): TaskRepository {
        return TaskRepository(taskDao, commentDao, repeatingTaskDao)
    }
}
