package com.boxbuilder.workplanner.ui.settings

import android.content.SharedPreferences
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.boxbuilder.workplanner.auth.GoogleAuthManager
import com.boxbuilder.workplanner.data.TaskRepository
import com.boxbuilder.workplanner.data.api.AuthInterceptor
import com.boxbuilder.workplanner.ui.theme.ThemeMode
import com.boxbuilder.workplanner.ui.theme.ThemePreferences
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val repository: TaskRepository,
    private val authManager: GoogleAuthManager,
    private val prefs: SharedPreferences,
    private val themePreferences: ThemePreferences
) : ViewModel() {

    val themeMode: StateFlow<ThemeMode> = themePreferences.mode

    fun setThemeMode(mode: ThemeMode) {
        themePreferences.setMode(mode)
    }

    fun signOut(onComplete: () -> Unit) {
        viewModelScope.launch {
            prefs.edit().remove(AuthInterceptor.PREF_JWT).apply()
            repository.clearAll()
            authManager.signOut()
            onComplete()
        }
    }
}
