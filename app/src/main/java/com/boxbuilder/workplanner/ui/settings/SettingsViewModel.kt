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
    val syncResult: String? = null,
    val isRestoring: Boolean = false,
    val restoreResult: String? = null
)

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val backupProcessorFactory: BackupProcessorFactory,
    @ApplicationContext private val context: Context
) : ViewModel() {

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    fun syncNow() {
        _uiState.value = _uiState.value.copy(isSyncing = true, syncResult = null)
        viewModelScope.launch {
            try {
                val processor = backupProcessorFactory.create()
                processor.performBackup()
                _uiState.value = _uiState.value.copy(isSyncing = false, syncResult = "Backup completed successfully")
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(isSyncing = false, syncResult = "Backup failed: ${e.message}")
            }
        }
    }

    fun restoreFromBackup() {
        _uiState.value = _uiState.value.copy(isRestoring = true, restoreResult = null)
        viewModelScope.launch {
            try {
                val processor = backupProcessorFactory.create()
                val found = processor.performRestore()
                _uiState.value = if (found) {
                    _uiState.value.copy(isRestoring = false, restoreResult = "Restore completed successfully")
                } else {
                    _uiState.value.copy(isRestoring = false, restoreResult = "No backup found on Drive")
                }
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(isRestoring = false, restoreResult = "Restore failed: ${e.message}")
            }
        }
    }

    fun clearResult() {
        _uiState.value = _uiState.value.copy(syncResult = null, restoreResult = null)
    }
}
