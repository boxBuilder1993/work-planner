package com.boxbuilder.workplanner.ui.auth

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.boxbuilder.workplanner.auth.EncryptionManager
import com.boxbuilder.workplanner.auth.GoogleAuthManager
import dagger.hilt.android.lifecycle.HiltViewModel
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
    private val encryptionManager: EncryptionManager
) : ViewModel() {

    private val _uiState = MutableStateFlow(AuthUiState())
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    init {
        if (authManager.isSignedIn) {
            if (encryptionManager.hasEncryptionKey) {
                // Fully set up — ready to use the app
                _uiState.value = AuthUiState(
                    isSignedIn = true,
                    isReady = true,
                    userName = authManager.userName,
                    userEmail = authManager.userEmail
                )
            } else {
                // Signed in but no encryption key — need passphrase setup
                // Phase 8 will add backup-exists check here; for now go straight to creation
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
                        needsPassphraseCreation = true,
                        userName = authManager.userName,
                        userEmail = authManager.userEmail
                    )
                    // Phase 8 will add: check Drive for backup
                    // If backup exists → needsPassphraseEntry = true instead
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
        // Phase 8 will upload the salt to Drive here
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

        encryptionManager.restoreKeyFromPassphrase(passphrase, salt)
        // Phase 8 will attempt to decrypt backup to verify passphrase is correct
        _uiState.value = _uiState.value.copy(
            needsPassphraseEntry = false,
            passphraseError = null,
            isReady = true
        )
    }

    fun skipRestore() {
        // User skips restore — create fresh passphrase instead
        _uiState.value = _uiState.value.copy(
            needsPassphraseEntry = false,
            needsPassphraseCreation = true,
            passphraseError = null
        )
    }

    fun signOut() {
        viewModelScope.launch {
            authManager.signOut()
            encryptionManager.clearKey()
            _uiState.value = AuthUiState()
        }
    }

    fun clearError() {
        _uiState.value = _uiState.value.copy(error = null, passphraseError = null)
    }
}
