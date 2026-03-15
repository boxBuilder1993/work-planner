package com.boxbuilder.workplanner.ui.settings

import android.content.SharedPreferences
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.boxbuilder.workplanner.auth.GoogleAuthManager
import com.boxbuilder.workplanner.data.TaskRepository
import com.boxbuilder.workplanner.data.api.AuthInterceptor
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val repository: TaskRepository,
    private val authManager: GoogleAuthManager,
    private val prefs: SharedPreferences
) : ViewModel() {

    fun signOut(onComplete: () -> Unit) {
        viewModelScope.launch {
            prefs.edit().remove(AuthInterceptor.PREF_JWT).apply()
            repository.clearAll()
            authManager.signOut()
            onComplete()
        }
    }
}
