package com.boxbuilder.workplanner.auth

import android.app.PendingIntent
import android.content.Context
import android.content.SharedPreferences
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import com.google.android.gms.auth.api.identity.AuthorizationRequest
import com.google.android.gms.auth.api.identity.Identity
import com.google.android.gms.common.api.Scope
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import kotlinx.coroutines.tasks.await

class GoogleAuthManager(
    private val context: Context,
    private val prefs: SharedPreferences
) {
    companion object {
        const val WEB_CLIENT_ID = "887974376217-gjbc077ed1s0v79gg6df1oue6sroaq99.apps.googleusercontent.com"

        private const val PREF_SIGNED_IN = "signed_in"
        private const val PREF_USER_EMAIL = "user_email"
        private const val PREF_USER_NAME = "user_name"
        private const val DRIVE_APPDATA_SCOPE = "https://www.googleapis.com/auth/drive.appdata"
    }

    private val credentialManager = CredentialManager.create(context)

    val isSignedIn: Boolean get() = prefs.getBoolean(PREF_SIGNED_IN, false)
    val userEmail: String? get() = prefs.getString(PREF_USER_EMAIL, null)
    val userName: String? get() = prefs.getString(PREF_USER_NAME, null)

    sealed class DriveAuthResult {
        data object Authorized : DriveAuthResult()
        data class NeedsConsent(val pendingIntent: PendingIntent) : DriveAuthResult()
    }

    suspend fun signIn(activityContext: Context): Result<Unit> {
        val googleIdOption = GetGoogleIdOption.Builder()
            .setServerClientId(WEB_CLIENT_ID)
            .setFilterByAuthorizedAccounts(false)
            .build()

        val request = GetCredentialRequest.Builder()
            .addCredentialOption(googleIdOption)
            .build()

        return try {
            val result = credentialManager.getCredential(activityContext, request)
            val googleIdToken = GoogleIdTokenCredential.createFrom(result.credential.data)
            val email = googleIdToken.email
                ?: throw IllegalStateException("Could not extract email from Google credential")

            prefs.edit()
                .putBoolean(PREF_SIGNED_IN, true)
                .putString(PREF_USER_EMAIL, email)
                .putString(PREF_USER_NAME, googleIdToken.displayName)
                .apply()

            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun requestDriveAuthorization(activityContext: Context): DriveAuthResult {
        val authorizationRequest = AuthorizationRequest.builder()
            .setRequestedScopes(listOf(Scope(DRIVE_APPDATA_SCOPE)))
            .build()

        val authorizationResult = Identity.getAuthorizationClient(activityContext)
            .authorize(authorizationRequest)
            .await()

        return if (authorizationResult.hasResolution()) {
            DriveAuthResult.NeedsConsent(authorizationResult.pendingIntent!!)
        } else {
            DriveAuthResult.Authorized
        }
    }

    suspend fun signOut() {
        credentialManager.clearCredentialState(ClearCredentialStateRequest())
        prefs.edit()
            .remove(PREF_SIGNED_IN)
            .remove(PREF_USER_EMAIL)
            .remove(PREF_USER_NAME)
            .apply()
    }
}
