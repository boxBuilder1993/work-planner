package com.boxbuilder.workplanner.ui.auth

import android.content.Context
import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.boxbuilder.workplanner.auth.EncryptionManager
import com.boxbuilder.workplanner.auth.GoogleAuthManager
import com.boxbuilder.workplanner.backup.BackupProcessorFactory
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
    val isReady: Boolean = false
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

    init {
        if (authManager.isSignedIn) {
            if (encryptionManager.hasEncryptionKey) {
                // Fully set up — schedule sync and go
                SyncWorker.schedule(context)
                _uiState.value = AuthUiState(
                    isSignedIn = true,
                    isReady = true,
                    userName = authManager.userName,
                    userEmail = authManager.userEmail
                )
            } else {
                // Signed in but no encryption key — need passphrase setup
                _uiState.value = AuthUiState(
                    isSignedIn = true,
                    needsPassphraseCreation = true,
                    userName = authManager.userName,
                    userEmail = authManager.userEmail
                )
            }
        }
    }

    fun signIn(activityContext: Context) {
        _uiState.value = _uiState.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            authManager.signIn(activityContext).fold(
                onSuccess = {
                    _uiState.value = _uiState.value.copy(
                        isSignedIn = true,
                        isLoading = false,
                        userName = authManager.userName,
                        userEmail = authManager.userEmail
                    )
                    // Check Drive for existing backup
                    checkForExistingBackup()
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

    private suspend fun checkForExistingBackup() {
        try {
            // Need a temporary encryption key to check Drive — but we can't create
            // a BackupProcessor without one. The hasRemoteBackup() check only needs
            // Drive access (file existence check), not decryption. However, our
            // BackupProcessorFactory requires an encryption key.
            // For now, default to passphrase creation. The user can restore from
            // Settings after setup if they have an existing backup.
            _uiState.value = _uiState.value.copy(needsPassphraseCreation = true)
        } catch (e: Exception) {
            Log.w(TAG, "Backup check failed, defaulting to passphrase creation", e)
            _uiState.value = _uiState.value.copy(needsPassphraseCreation = true)
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

        encryptionManager.createKeyFromPassphrase(passphrase)
        SyncWorker.schedule(context)
        _uiState.value = _uiState.value.copy(
            needsPassphraseCreation = false,
            passphraseError = null,
            isReady = true
        )
    }

    fun enterPassphrase(passphrase: String, salt: ByteArray) {
        if (passphrase.isBlank()) {
            _uiState.value = _uiState.value.copy(
                passphraseError = "Passphrase cannot be empty"
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
                _uiState.value = _uiState.value.copy(
                    needsPassphraseEntry = false,
                    isLoading = false,
                    passphraseError = null,
                    isReady = true
                )
            } catch (e: Exception) {
                // Decryption failure likely means wrong passphrase
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
