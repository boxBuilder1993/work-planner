package com.boxbuilder.workplanner.ui.settings

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.boxbuilder.workplanner.backup.BackupProcessorFactory
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SettingsUiState(
    val isSyncing: Boolean = false,
    val isRestoring: Boolean = false,
    val statusMessage: String? = null,
    val isStatusError: Boolean = false
)

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val backupProcessorFactory: BackupProcessorFactory,
    @ApplicationContext private val context: Context
) : ViewModel() {

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    fun syncNow() {
        _uiState.value = _uiState.value.copy(isSyncing = true, statusMessage = null)
        viewModelScope.launch {
            try {
                val processor = backupProcessorFactory.create()
                processor.performBackup()
                _uiState.value = _uiState.value.copy(isSyncing = false, statusMessage = "Backup completed successfully", isStatusError = false)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(isSyncing = false, statusMessage = "Backup failed: ${e.message}", isStatusError = true)
            }
        }
    }

    fun restoreFromBackup() {
        _uiState.value = _uiState.value.copy(isRestoring = true, statusMessage = null)
        viewModelScope.launch {
            try {
                val processor = backupProcessorFactory.create()
                val found = processor.performRestore()
                _uiState.value = _uiState.value.copy(
                    isRestoring = false,
                    statusMessage = if (found) "Restore completed successfully" else "No backup found on Drive",
                    isStatusError = !found
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(isRestoring = false, statusMessage = "Restore failed: ${e.message}", isStatusError = true)
            }
        }
    }

    fun clearResult() {
        _uiState.value = _uiState.value.copy(statusMessage = null)
    }
}
