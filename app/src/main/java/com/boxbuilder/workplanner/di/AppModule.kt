package com.boxbuilder.workplanner.di

import android.content.SharedPreferences
import com.boxbuilder.workplanner.data.TaskRepository
import com.boxbuilder.workplanner.data.api.AuthInterceptor
import com.boxbuilder.workplanner.data.api.WorkPlannerApi
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    // Emulator localhost; change for production
    private const val BASE_URL = "http://10.0.2.2:8080/"

    @Provides
    @Singleton
    fun provideOkHttpClient(prefs: SharedPreferences): OkHttpClient {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        }
        return OkHttpClient.Builder()
            .addInterceptor(AuthInterceptor(prefs))
            .addInterceptor(logging)
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient): Retrofit {
        return Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }

    @Provides
    @Singleton
    fun provideWorkPlannerApi(retrofit: Retrofit): WorkPlannerApi {
        return retrofit.create(WorkPlannerApi::class.java)
    }

    @Provides
    @Singleton
    fun provideTaskRepository(api: WorkPlannerApi): TaskRepository {
        return TaskRepository(api)
    }
}
