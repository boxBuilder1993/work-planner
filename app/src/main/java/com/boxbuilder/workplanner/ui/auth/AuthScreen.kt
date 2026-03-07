package com.boxbuilder.workplanner.ui.auth

import android.app.Activity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun AuthScreen(
    onAuthComplete: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current

    // Launcher for Drive consent PendingIntent
    val consentLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.StartIntentSenderForResult()
    ) { result ->
        viewModel.onDriveConsentResult(result.resultCode == Activity.RESULT_OK)
    }

    // Launch consent dialog when ViewModel provides a PendingIntent
    LaunchedEffect(uiState.driveConsentIntent) {
        uiState.driveConsentIntent?.let { pendingIntent ->
            consentLauncher.launch(
                IntentSenderRequest.Builder(pendingIntent.intentSender).build()
            )
        }
    }

    // Complete auth when ready
    LaunchedEffect(uiState.isReady) {
        if (uiState.isReady) onAuthComplete()
    }

    // If signed in but needs Drive auth (deferred from init), trigger it now
    LaunchedEffect(uiState.isSignedIn, uiState.isLoading) {
        viewModel.requestDriveAuthorizationIfNeeded(context)
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        contentAlignment = Alignment.Center
    ) {
        when {
            uiState.isLoading -> {
                CircularProgressIndicator()
            }
            uiState.needsPassphraseCreation -> {
                PassphraseCreationContent(
                    error = uiState.passphraseError,
                    onCreatePassphrase = viewModel::createPassphrase
                )
            }
            uiState.needsPassphraseEntry -> {
                PassphraseEntryContent(
                    error = uiState.passphraseError,
                    onEnterPassphrase = { passphrase ->
                        viewModel.enterPassphrase(passphrase)
                    },
                    onSkip = viewModel::skipRestore
                )
            }
            else -> {
                SignInContent(
                    error = uiState.error,
                    onSignIn = viewModel::signIn
                )
            }
        }
    }
}

@Composable
private fun SignInContent(
    error: String?,
    onSignIn: (android.content.Context) -> Unit
) {
    val context = LocalContext.current

    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(
            text = "WorkPlanner",
            style = MaterialTheme.typography.headlineLarge
        )
        Spacer(modifier = Modifier.height(32.dp))
        Button(
            onClick = { onSignIn(context) },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Sign in with Google")
        }
        if (error != null) {
            Text(
                text = error,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

@Composable
private fun PassphraseCreationContent(
    error: String?,
    onCreatePassphrase: (String, String) -> Unit
) {
    var passphrase by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }

    Column(
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(
            text = "Create a backup passphrase",
            style = MaterialTheme.typography.headlineSmall
        )
        Text(
            text = "This passphrase encrypts your data on Google Drive. " +
                "You'll need it to restore on a new device.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(8.dp))
        OutlinedTextField(
            value = passphrase,
            onValueChange = { passphrase = it },
            label = { Text("Passphrase") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        OutlinedTextField(
            value = confirm,
            onValueChange = { confirm = it },
            label = { Text("Confirm passphrase") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        if (error != null) {
            Text(
                text = error,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall
            )
        }
        Text(
            text = "If you forget this passphrase, your backup cannot be recovered.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.error
        )
        Spacer(modifier = Modifier.height(8.dp))
        Button(
            onClick = { onCreatePassphrase(passphrase, confirm) },
            modifier = Modifier.fillMaxWidth(),
            enabled = passphrase.isNotBlank() && confirm.isNotBlank()
        ) {
            Text("Continue")
        }
    }
}

@Composable
private fun PassphraseEntryContent(
    error: String?,
    onEnterPassphrase: (String) -> Unit,
    onSkip: () -> Unit
) {
    var passphrase by remember { mutableStateOf("") }

    Column(
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(
            text = "Backup found on Drive",
            style = MaterialTheme.typography.headlineSmall
        )
        Text(
            text = "Enter your passphrase to restore your data:",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(8.dp))
        OutlinedTextField(
            value = passphrase,
            onValueChange = { passphrase = it },
            label = { Text("Passphrase") },
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        if (error != null) {
            Text(
                text = error,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall
            )
        }
        Spacer(modifier = Modifier.height(8.dp))
        Button(
            onClick = { onEnterPassphrase(passphrase) },
            modifier = Modifier.fillMaxWidth(),
            enabled = passphrase.isNotBlank()
        ) {
            Text("Restore")
        }
        OutlinedButton(
            onClick = onSkip,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Skip")
        }
    }
}
