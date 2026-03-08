package com.boxbuilder.workplanner.ui.auth

import android.app.PendingIntent
import android.content.Context
import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.boxbuilder.workplanner.auth.EncryptionManager
import com.boxbuilder.workplanner.auth.GoogleAuthManager
import com.boxbuilder.workplanner.backup.BackupProcessorFactory
import com.boxbuilder.workplanner.backup.RecurringTaskWorker
import com.boxbuilder.workplanner.backup.SyncWorker
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class AuthUiState(
    val isSignedIn: Boolean = false,
    val isLoading: Boolean = false,
    val hasCloudBackup: Boolean = false,
    val needsPassphraseCreation: Boolean = false,
    val needsPassphraseEntry: Boolean = false,
    val passphraseError: String? = null,
    val error: String? = null,
    val userName: String? = null,
    val userEmail: String? = null,
    val isReady: Boolean = false,
    val driveConsentIntent: PendingIntent? = null
)

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authManager: GoogleAuthManager,
    private val encryptionManager: EncryptionManager,
    private val backupProcessorFactory: BackupProcessorFactory,
    @ApplicationContext private val context: Context
) : ViewModel() {

    private val _uiState = MutableStateFlow(AuthUiState())
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    private var remoteSalt: ByteArray? = null
    private var pendingActivityContext: Context? = null

    init {
        if (authManager.isSignedIn) {
            if (encryptionManager.hasEncryptionKey) {
                SyncWorker.schedule(context)
                RecurringTaskWorker.schedule(context)
                _uiState.value = AuthUiState(
                    isSignedIn = true,
                    isReady = true,
                    userName = authManager.userName,
                    userEmail = authManager.userEmail
                )
            } else {
                // Signed in but no encryption key — need to authorize Drive and check backup.
                // Drive authorization requires an Activity context, so we defer until
                // the UI calls requestDriveAuthorizationIfNeeded().
                _uiState.value = AuthUiState(
                    isSignedIn = true,
                    isLoading = true,
                    userName = authManager.userName,
                    userEmail = authManager.userEmail
                )
            }
        }
    }

    /**
     * Called by the UI once an Activity context is available, to complete the
     * Drive authorization + backup check flow that was deferred from init.
     */
    fun requestDriveAuthorizationIfNeeded(activityContext: Context) {
        val state = _uiState.value
        if (state.isSignedIn && state.isLoading && !state.isReady &&
            !state.needsPassphraseCreation && !state.needsPassphraseEntry
        ) {
            pendingActivityContext = activityContext
            viewModelScope.launch {
                requestDriveAuthAndCheckBackup(activityContext)
            }
        }
    }

    fun signIn(activityContext: Context) {
        _uiState.value = _uiState.value.copy(isLoading = true, error = null)
        pendingActivityContext = activityContext
        viewModelScope.launch {
            authManager.signIn(activityContext).fold(
                onSuccess = {
                    _uiState.value = _uiState.value.copy(
                        isSignedIn = true,
                        userName = authManager.userName,
                        userEmail = authManager.userEmail
                    )
                    requestDriveAuthAndCheckBackup(activityContext)
                },
                onFailure = { e ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        error = e.message ?: "Sign-in failed"
                    )
                }
            )
        }
    }

    private suspend fun requestDriveAuthAndCheckBackup(activityContext: Context) {
        _uiState.value = _uiState.value.copy(isLoading = true)
        try {
            when (val result = authManager.requestDriveAuthorization(activityContext)) {
                is GoogleAuthManager.DriveAuthResult.Authorized -> {
                    checkForExistingBackup()
                }
                is GoogleAuthManager.DriveAuthResult.NeedsConsent -> {
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        driveConsentIntent = result.pendingIntent
                    )
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Drive authorization failed", e)
            _uiState.value = _uiState.value.copy(
                isLoading = false,
                error = "Drive authorization failed: ${e.message}"
            )
        }
    }

    fun onDriveConsentResult(granted: Boolean) {
        _uiState.value = _uiState.value.copy(driveConsentIntent = null)
        if (granted) {
            viewModelScope.launch {
                checkForExistingBackup()
            }
        } else {
            _uiState.value = _uiState.value.copy(
                error = "Drive access is required for backup. Please try again."
            )
        }
    }

    private suspend fun checkForExistingBackup() {
        _uiState.value = _uiState.value.copy(isLoading = true)
        try {
            val hasBackup = backupProcessorFactory.hasRemoteBackup()
            if (hasBackup) {
                remoteSalt = backupProcessorFactory.downloadSalt()
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    needsPassphraseEntry = true,
                    hasCloudBackup = true
                )
            } else {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    needsPassphraseCreation = true
                )
            }
        } catch (e: Exception) {
            Log.w(TAG, "Backup check failed, defaulting to passphrase creation", e)
            _uiState.value = _uiState.value.copy(
                isLoading = false,
                needsPassphraseCreation = true
            )
        }
    }

    fun createPassphrase(passphrase: String, confirm: String) {
        if (passphrase.length < 8) {
            _uiState.value = _uiState.value.copy(
                passphraseError = "Passphrase must be at least 8 characters"
            )
            return
        }
        if (passphrase != confirm) {
            _uiState.value = _uiState.value.copy(
                passphraseError = "Passphrases do not match"
            )
            return
        }

        _uiState.value = _uiState.value.copy(isLoading = true, passphraseError = null)
        val salt = encryptionManager.createKeyFromPassphrase(passphrase)
        viewModelScope.launch {
            try {
                backupProcessorFactory.uploadSalt(salt)
                SyncWorker.schedule(context)
                RecurringTaskWorker.schedule(context)
                _uiState.value = _uiState.value.copy(
                    needsPassphraseCreation = false,
                    isLoading = false,
                    passphraseError = null,
                    isReady = true
                )
            } catch (e: Exception) {
                Log.e(TAG, "Failed to upload salt to Drive", e)
                encryptionManager.clearKey()
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    passphraseError = "Failed to upload encryption salt to Drive: ${e.message}"
                )
            }
        }
    }

    fun enterPassphrase(passphrase: String) {
        if (passphrase.isBlank()) {
            _uiState.value = _uiState.value.copy(
                passphraseError = "Passphrase cannot be empty"
            )
            return
        }

        val salt = remoteSalt
        if (salt == null) {
            _uiState.value = _uiState.value.copy(
                passphraseError = "Could not retrieve encryption salt from Drive"
            )
            return
        }

        _uiState.value = _uiState.value.copy(isLoading = true, passphraseError = null)
        encryptionManager.restoreKeyFromPassphrase(passphrase, salt)

        viewModelScope.launch {
            try {
                val processor = backupProcessorFactory.create()
                processor.performRestore()
                SyncWorker.schedule(context)
                RecurringTaskWorker.schedule(context)
                _uiState.value = _uiState.value.copy(
                    needsPassphraseEntry = false,
                    isLoading = false,
                    passphraseError = null,
                    isReady = true
                )
            } catch (e: Exception) {
                encryptionManager.clearKey()
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    passphraseError = "Incorrect passphrase or restore failed"
                )
            }
        }
    }

    fun skipRestore() {
        _uiState.value = _uiState.value.copy(
            needsPassphraseEntry = false,
            needsPassphraseCreation = true,
            passphraseError = null
        )
    }

    fun signOut() {
        viewModelScope.launch {
            SyncWorker.cancel(context)
            RecurringTaskWorker.cancel(context)
            authManager.signOut()
            encryptionManager.clearKey()
            _uiState.value = AuthUiState()
        }
    }

    fun clearError() {
        _uiState.value = _uiState.value.copy(error = null, passphraseError = null)
    }

    companion object {
        private const val TAG = "AuthViewModel"
    }
}
