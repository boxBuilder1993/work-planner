package com.boxbuilder.workplanner.backup

import android.content.Context
import com.boxbuilder.workplanner.auth.EncryptionManager
import com.boxbuilder.workplanner.auth.GoogleAuthManager
import com.boxbuilder.workplanner.backup.gdrive.GDriveKVStore
import com.boxbuilder.workplanner.data.dao.CommentDao
import com.boxbuilder.workplanner.data.dao.TaskDao
import com.boxbuilder.workplanner.generic.kvstore.EncryptionConfig
import com.google.api.client.googleapis.extensions.android.gms.auth.GoogleAccountCredential
import com.google.api.client.http.javanet.NetHttpTransport
import com.google.api.client.json.gson.GsonFactory
import com.google.api.services.drive.Drive
import com.google.api.services.drive.DriveScopes
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class BackupProcessorFactory @Inject constructor(
    @ApplicationContext private val context: Context,
    private val authManager: GoogleAuthManager,
    private val encryptionManager: EncryptionManager,
    private val taskDao: TaskDao,
    private val commentDao: CommentDao
) {
    fun create(): BackupProcessor {
        val credential = GoogleAccountCredential.usingOAuth2(
            context, listOf(DriveScopes.DRIVE_APPDATA)
        ).apply {
            selectedAccountName = authManager.userEmail
                ?: throw IllegalStateException("User not signed in")
        }

        val driveService = Drive.Builder(
            NetHttpTransport(), GsonFactory.getDefaultInstance(), credential
        ).setApplicationName("WorkPlanner").build()

        val key = encryptionManager.getEncryptionKey()
            ?: throw IllegalStateException("No encryption key available")
        val config = EncryptionConfig(key)

        val kvStore = GDriveKVStore(driveService, config, "workplanner")
        return BackupProcessor(taskDao, commentDao, kvStore)
    }
}
