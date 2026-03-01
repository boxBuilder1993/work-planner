package com.boxbuilder.workplanner.auth

import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec

class EncryptionManager(
    private val prefs: SharedPreferences
) {
    companion object {
        private const val KEYSTORE_ALIAS = "workplanner_wrapper_key"
        private const val PREF_ENCRYPTED_KEY = "encrypted_key"
        private const val PREF_ENCRYPTED_KEY_IV = "encrypted_key_iv"
        private const val PREF_SALT = "encryption_salt"
        private const val PBKDF2_ITERATIONS = 210_000
        private const val KEY_LENGTH_BITS = 256
        private const val SALT_LENGTH_BYTES = 16
        private const val GCM_TAG_LENGTH = 128
    }

    val hasEncryptionKey: Boolean get() = prefs.contains(PREF_ENCRYPTED_KEY)

    val salt: ByteArray?
        get() = prefs.getString(PREF_SALT, null)?.let {
            Base64.decode(it, Base64.NO_WRAP)
        }

    /**
     * Create a new encryption key from a passphrase. Generates a random salt,
     * derives the key via PBKDF2, and stores it wrapped by an Android Keystore key.
     * Returns the salt (caller should persist it to Drive for cross-device restore).
     */
    fun createKeyFromPassphrase(passphrase: String): ByteArray {
        val newSalt = ByteArray(SALT_LENGTH_BYTES).also { SecureRandom().nextBytes(it) }
        val derivedKey = deriveKey(passphrase, newSalt)
        storeKey(derivedKey, newSalt)
        return newSalt
    }

    /**
     * Restore the encryption key from a passphrase + existing salt (e.g. downloaded from Drive).
     */
    fun restoreKeyFromPassphrase(passphrase: String, existingSalt: ByteArray) {
        val derivedKey = deriveKey(passphrase, existingSalt)
        storeKey(derivedKey, existingSalt)
    }

    /**
     * Retrieve the stored encryption key (decrypted via Android Keystore wrapper key).
     * Returns null if no key has been stored.
     */
    fun getEncryptionKey(): ByteArray? {
        return loadKey()
    }

    fun clearKey() {
        prefs.edit()
            .remove(PREF_ENCRYPTED_KEY)
            .remove(PREF_ENCRYPTED_KEY_IV)
            .remove(PREF_SALT)
            .apply()

        val keyStore = KeyStore.getInstance("AndroidKeyStore")
        keyStore.load(null)
        if (keyStore.containsAlias(KEYSTORE_ALIAS)) {
            keyStore.deleteEntry(KEYSTORE_ALIAS)
        }
    }

    private fun deriveKey(passphrase: String, salt: ByteArray): ByteArray {
        val factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
        val spec = PBEKeySpec(passphrase.toCharArray(), salt, PBKDF2_ITERATIONS, KEY_LENGTH_BITS)
        return factory.generateSecret(spec).encoded
    }

    private fun storeKey(key: ByteArray, salt: ByteArray) {
        val wrapperKey = getOrCreateWrapperKey()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, wrapperKey)
        val encrypted = cipher.doFinal(key)
        val iv = cipher.iv

        prefs.edit()
            .putString(PREF_ENCRYPTED_KEY, Base64.encodeToString(encrypted, Base64.NO_WRAP))
            .putString(PREF_ENCRYPTED_KEY_IV, Base64.encodeToString(iv, Base64.NO_WRAP))
            .putString(PREF_SALT, Base64.encodeToString(salt, Base64.NO_WRAP))
            .apply()
    }

    private fun loadKey(): ByteArray? {
        val encryptedB64 = prefs.getString(PREF_ENCRYPTED_KEY, null) ?: return null
        val ivB64 = prefs.getString(PREF_ENCRYPTED_KEY_IV, null) ?: return null

        val encrypted = Base64.decode(encryptedB64, Base64.NO_WRAP)
        val iv = Base64.decode(ivB64, Base64.NO_WRAP)

        val wrapperKey = getOrCreateWrapperKey()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, wrapperKey, GCMParameterSpec(GCM_TAG_LENGTH, iv))
        return cipher.doFinal(encrypted)
    }

    private fun getOrCreateWrapperKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore")
        keyStore.load(null)

        if (keyStore.containsAlias(KEYSTORE_ALIAS)) {
            return (keyStore.getEntry(KEYSTORE_ALIAS, null) as KeyStore.SecretKeyEntry).secretKey
        }

        val keyGenerator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            "AndroidKeyStore"
        )
        keyGenerator.init(
            KeyGenParameterSpec.Builder(
                KEYSTORE_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return keyGenerator.generateKey()
    }
}
