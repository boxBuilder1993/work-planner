package com.boxbuilder.workplanner.di

import android.content.Context
import androidx.room.Room
import com.boxbuilder.workplanner.data.TaskRepository
import com.boxbuilder.workplanner.data.dao.CommentDao
import com.boxbuilder.workplanner.data.dao.TaskDao
import com.boxbuilder.workplanner.data.room.WorkPlannerDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

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
        ).build()
    }

    @Provides
    fun provideTaskDao(db: WorkPlannerDatabase): TaskDao = db.roomTaskDao()

    @Provides
    fun provideCommentDao(db: WorkPlannerDatabase): CommentDao = db.roomCommentDao()

    @Provides
    @Singleton
    fun provideTaskRepository(taskDao: TaskDao, commentDao: CommentDao): TaskRepository {
        return TaskRepository(taskDao, commentDao)
    }
}
