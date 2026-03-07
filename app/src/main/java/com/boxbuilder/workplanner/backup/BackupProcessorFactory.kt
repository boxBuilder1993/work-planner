package com.boxbuilder.workplanner.backup

import android.accounts.Account
import android.content.Context
import com.boxbuilder.workplanner.auth.EncryptionManager
import com.boxbuilder.workplanner.auth.GoogleAuthManager
import com.boxbuilder.workplanner.backup.gdrive.GDriveKVStore
import com.boxbuilder.workplanner.data.dao.CommentDao
import com.boxbuilder.workplanner.data.dao.TaskDao
import com.boxbuilder.workplanner.generic.kvstore.EncryptionConfig
import com.google.api.client.googleapis.extensions.android.gms.auth.GoogleAccountCredential
import com.google.api.client.http.ByteArrayContent
import com.google.api.client.http.javanet.NetHttpTransport
import com.google.api.client.json.gson.GsonFactory
import com.google.api.services.drive.Drive
import com.google.api.services.drive.DriveScopes
import com.google.api.services.drive.model.File
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.ByteArrayOutputStream
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
    private fun createDriveService(): Drive {
        val email = authManager.userEmail
            ?: throw IllegalStateException("User not signed in")

        // Use setSelectedAccount(Account) instead of setSelectedAccountName(String).
        // setSelectedAccountName looks up the account in AccountManager and silently
        // sets it to null if the account isn't registered on the device. With Credential
        // Manager sign-in, the Google account may not be in AccountManager.
        val credential = GoogleAccountCredential.usingOAuth2(
            context, listOf(DriveScopes.DRIVE_APPDATA)
        )
        credential.selectedAccount = Account(email, "com.google")

        return Drive.Builder(
            NetHttpTransport(), GsonFactory.getDefaultInstance(), credential
        ).setApplicationName("WorkPlanner").build()
    }

    fun create(): BackupProcessor {
        val driveService = createDriveService()

        val key = encryptionManager.getEncryptionKey()
            ?: throw IllegalStateException("No encryption key available")
        val config = EncryptionConfig(key)

        val kvStore = GDriveKVStore(driveService, config, "workplanner")
        return BackupProcessor(taskDao, commentDao, kvStore)
    }

    suspend fun hasRemoteBackup(): Boolean = withContext(Dispatchers.IO) {
        val driveService = createDriveService()
        val result = driveService.files().list()
            .setQ("name = 'workplanner_tasks.enc'")
            .setSpaces("appDataFolder")
            .setFields("files(id)")
            .execute()
        !result.files.isNullOrEmpty()
    }

    suspend fun uploadSalt(salt: ByteArray) = withContext(Dispatchers.IO) {
        val driveService = createDriveService()
        val fileName = "workplanner_salt.bin"
        val content = ByteArrayContent("application/octet-stream", salt)

        val existingId = findFileId(driveService, fileName)
        if (existingId != null) {
            driveService.files().update(existingId, null, content).execute()
        } else {
            val metadata = File().apply {
                name = fileName
                parents = listOf("appDataFolder")
            }
            driveService.files().create(metadata, content)
                .setFields("id")
                .execute()
        }
    }

    suspend fun downloadSalt(): ByteArray? = withContext(Dispatchers.IO) {
        val driveService = createDriveService()
        val fileId = findFileId(driveService, "workplanner_salt.bin") ?: return@withContext null
        val outputStream = ByteArrayOutputStream()
        driveService.files().get(fileId).executeMediaAndDownloadTo(outputStream)
        outputStream.toByteArray()
    }

    private fun findFileId(driveService: Drive, fileName: String): String? {
        val result = driveService.files().list()
            .setQ("name = '$fileName'")
            .setSpaces("appDataFolder")
            .setFields("files(id)")
            .execute()
        return result.files?.firstOrNull()?.id
    }
}
