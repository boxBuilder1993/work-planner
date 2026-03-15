package com.boxbuilder.workplanner.auth

import android.content.Context
import android.content.SharedPreferences
import androidx.credentials.ClearCredentialStateRequest
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import com.boxbuilder.workplanner.BuildConfig
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential

class GoogleAuthManager(
    private val context: Context,
    private val prefs: SharedPreferences
) {
    companion object {
        private const val PREF_SIGNED_IN = "signed_in"
        private const val PREF_USER_EMAIL = "user_email"
        private const val PREF_USER_NAME = "user_name"
    }

    private val credentialManager = CredentialManager.create(context)

    val isSignedIn: Boolean get() = prefs.getBoolean(PREF_SIGNED_IN, false)
    val userEmail: String? get() = prefs.getString(PREF_USER_EMAIL, null)
    val userName: String? get() = prefs.getString(PREF_USER_NAME, null)

    /**
     * Signs in with Google and returns the ID token for backend exchange.
     */
    suspend fun signIn(activityContext: Context): Result<String> {
        val googleIdOption = GetGoogleIdOption.Builder()
            .setServerClientId(BuildConfig.GOOGLE_CLIENT_ID)
            .setFilterByAuthorizedAccounts(false)
            .build()

        val request = GetCredentialRequest.Builder()
            .addCredentialOption(googleIdOption)
            .build()

        return try {
            val result = credentialManager.getCredential(activityContext, request)
            val googleIdToken = GoogleIdTokenCredential.createFrom(result.credential.data)
            val idToken = googleIdToken.idToken
            val email = googleIdToken.email
                ?: throw IllegalStateException("Could not extract email from Google credential")

            prefs.edit()
                .putBoolean(PREF_SIGNED_IN, true)
                .putString(PREF_USER_EMAIL, email)
                .putString(PREF_USER_NAME, googleIdToken.displayName)
                .apply()

            Result.success(idToken)
        } catch (e: Exception) {
            Result.failure(e)
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
