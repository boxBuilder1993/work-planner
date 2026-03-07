package com.boxbuilder.workplanner.di

import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

@Module
@InstallIn(SingletonComponent::class)
object BackupModule {
    // BackupProcessorFactory uses @Inject constructor and is automatically
    // provided by Hilt — no manual @Provides needed.
    //
    // The factory pattern avoids eagerly constructing Drive/EncryptionConfig
    // at app startup (when the user may not be signed in or have a passphrase).
    // Instead, BackupProcessor is created on-demand when backup is triggered.
}
