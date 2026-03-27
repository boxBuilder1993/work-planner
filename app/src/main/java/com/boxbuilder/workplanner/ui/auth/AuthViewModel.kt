package com.boxbuilder.workplanner.ui.auth

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.boxbuilder.workplanner.auth.GoogleAuthManager
import com.boxbuilder.workplanner.data.TaskRepository
import com.boxbuilder.workplanner.data.api.AuthInterceptor
import com.boxbuilder.workplanner.data.api.WorkPlannerApi
import com.boxbuilder.workplanner.data.api.dto.AuthRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class AuthUiState(
    val isSignedIn: Boolean = false,
    val isLoading: Boolean = false,
    val error: String? = null,
    val userName: String? = null,
    val userEmail: String? = null,
    val isReady: Boolean = false
)

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val authManager: GoogleAuthManager,
    private val api: WorkPlannerApi,
    private val repository: TaskRepository,
    private val prefs: SharedPreferences
) : ViewModel() {

    private val _uiState = MutableStateFlow(AuthUiState())
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    init {
        val jwt = prefs.getString(AuthInterceptor.PREF_JWT, null)
        if (authManager.isSignedIn && jwt != null) {
            _uiState.value = AuthUiState(
                isSignedIn = true,
                isLoading = true,
                userName = authManager.userName,
                userEmail = authManager.userEmail
            )
            viewModelScope.launch {
                repository.initialize()
                _uiState.value = AuthUiState(
                    isSignedIn = true,
                    isLoading = false,
                    isReady = true,
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
                onSuccess = { idToken ->
                    exchangeToken(idToken)
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

    private suspend fun exchangeToken(idToken: String) {
        try {
            val response = api.authGoogle(AuthRequest(idToken = idToken))
            prefs.edit()
                .putString(AuthInterceptor.PREF_JWT, response.token)
                .apply()

            repository.initialize()

            _uiState.value = AuthUiState(
                isSignedIn = true,
                isReady = true,
                userName = authManager.userName,
                userEmail = authManager.userEmail
            )
        } catch (e: Exception) {
            Log.e(TAG, "Token exchange failed", e)
            _uiState.value = _uiState.value.copy(
                isLoading = false,
                error = "Authentication failed: ${e.message}"
            )
        }
    }

    fun signOut() {
        viewModelScope.launch {
            prefs.edit().remove(AuthInterceptor.PREF_JWT).apply()
            repository.clearAll()
            authManager.signOut()
            _uiState.value = AuthUiState()
        }
    }

    fun clearError() {
        _uiState.value = _uiState.value.copy(error = null)
    }

    companion object {
        private const val TAG = "AuthViewModel"
    }
}
