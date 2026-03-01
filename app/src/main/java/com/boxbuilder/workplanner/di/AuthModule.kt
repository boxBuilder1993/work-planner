package com.boxbuilder.workplanner.di

import android.content.Context
import android.content.SharedPreferences
import com.boxbuilder.workplanner.auth.EncryptionManager
import com.boxbuilder.workplanner.auth.GoogleAuthManager
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AuthModule {

    @Provides
    @Singleton
    fun provideSharedPreferences(@ApplicationContext context: Context): SharedPreferences {
        return context.getSharedPreferences("workplanner_prefs", Context.MODE_PRIVATE)
    }

    @Provides
    @Singleton
    fun provideGoogleAuthManager(
        @ApplicationContext context: Context,
        prefs: SharedPreferences
    ): GoogleAuthManager {
        return GoogleAuthManager(context, prefs)
    }

    @Provides
    @Singleton
    fun provideEncryptionManager(prefs: SharedPreferences): EncryptionManager {
        return EncryptionManager(prefs)
    }
}
