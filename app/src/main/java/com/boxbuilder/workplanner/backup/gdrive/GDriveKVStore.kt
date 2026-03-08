package com.boxbuilder.workplanner.backup.gdrive

import com.boxbuilder.workplanner.generic.kvstore.EncryptionConfig
import com.boxbuilder.workplanner.generic.kvstore.EntityRegistration
import com.boxbuilder.workplanner.generic.kvstore.KVStore
import com.google.api.client.http.ByteArrayContent
import com.google.api.services.drive.Drive
import com.google.api.services.drive.model.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.encodeToJsonElement
import kotlinx.serialization.json.jsonObject
import java.io.ByteArrayOutputStream
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

class GDriveKVStore(
    private val driveService: Drive,
    private val encryptionConfig: EncryptionConfig,
    private val folderName: String
) : KVStore() {

    private val serializers = mutableMapOf<String, KSerializer<*>>()

    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }

    override fun <T : Any> registerEntity(entityName: String, registration: EntityRegistration<T>) {
        super.registerEntity(entityName, registration)

        val serializer = registration.serializer
            ?: throw IllegalArgumentException(
                "Entity '$entityName' must provide a serializer for GDriveKVStore"
            )
        serializers[entityName] = serializer
    }

    // ── Core operations ──────────────────────────────────────

    override suspend fun <T : Any> save(entity: String, value: T) = withContext(Dispatchers.IO) {
        val storageKey = deriveStorageKey(entity, value)
        val existing = downloadAndDecryptMap<T>(entity)
        val updated = existing.toMutableMap()
        updated[storageKey] = value
        encryptAndUpload(entity, serializeMap(entity, updated))
    }

    override suspend fun <T : Any> saveAll(entity: String, values: List<T>) = withContext(Dispatchers.IO) {
        val map = values.associateBy { deriveStorageKey(entity, it) }
        encryptAndUpload(entity, serializeMap(entity, map))
    }

    override suspend fun <T : Any> get(entity: String, id: String): T? = withContext(Dispatchers.IO) {
        val map = downloadAndDecryptMap<T>(entity)
        map[id]
    }

    override suspend fun <T : Any> getAll(entity: String): List<T> = withContext(Dispatchers.IO) {
        val map = downloadAndDecryptMap<T>(entity)
        map.values.toList()
    }

    override suspend fun <T : Any> getByIndex(
        entity: String,
        indexName: String,
        indexValues: Map<String, String>
    ): List<T> = withContext(Dispatchers.IO) {
        validateQueryKeys(entity, indexName, indexValues.keys)
        val all = getAll<T>(entity)
        all.filter { item ->
            val extracted = extractIndexValues(entity, indexName, item)
            extracted == indexValues
        }
    }

    override suspend fun delete(entity: String, id: String) = withContext(Dispatchers.IO) {
        val map = downloadAndDecryptMap<Any>(entity)
        if (map.containsKey(id)) {
            val updated = map.toMutableMap()
            updated.remove(id)
            if (updated.isEmpty()) {
                deleteFile(fileName(entity))
            } else {
                encryptAndUpload(entity, serializeMap(entity, updated))
            }
        }
    }

    override suspend fun deleteAll(entity: String) = withContext(Dispatchers.IO) {
        deleteFile(fileName(entity))
    }

    override suspend fun exists(entity: String): Boolean = withContext(Dispatchers.IO) {
        findFileId(fileName(entity)) != null
    }

    // ── Serialization helpers ────────────────────────────────

    @Suppress("UNCHECKED_CAST")
    private fun <T : Any> getSerializer(entityName: String): KSerializer<T> {
        return serializers[entityName] as? KSerializer<T>
            ?: throw IllegalStateException("No serializer for entity '$entityName'")
    }

    private fun <T : Any> serializeMap(entityName: String, map: Map<String, T>): ByteArray {
        val serializer = getSerializer<T>(entityName)
        val jsonObject = buildJsonObject {
            map.forEach { (key, value) ->
                put(key, json.encodeToJsonElement(serializer, value))
            }
        }
        return json.encodeToString(JsonObject.serializer(), jsonObject).toByteArray(Charsets.UTF_8)
    }

    private fun <T : Any> deserializeMap(entityName: String, bytes: ByteArray): Map<String, T> {
        val serializer = getSerializer<T>(entityName)
        val jsonObject = json.parseToJsonElement(String(bytes, Charsets.UTF_8)).jsonObject
        return jsonObject.mapValues { (_, element) ->
            json.decodeFromJsonElement(serializer, element)
        }
    }

    // ── Encryption helpers ───────────────────────────────────

    private fun encrypt(plainBytes: ByteArray): ByteArray {
        val iv = ByteArray(encryptionConfig.ivLengthBytes)
        SecureRandom().nextBytes(iv)

        val secretKey = SecretKeySpec(encryptionConfig.key, "AES")
        val cipher = Cipher.getInstance(encryptionConfig.algorithm)
        cipher.init(
            Cipher.ENCRYPT_MODE,
            secretKey,
            GCMParameterSpec(encryptionConfig.tagLengthBits, iv)
        )
        val ciphertext = cipher.doFinal(plainBytes)

        // Format: [IV][ciphertext + auth tag]
        return iv + ciphertext
    }

    private fun decrypt(encryptedBytes: ByteArray): ByteArray {
        val iv = encryptedBytes.copyOfRange(0, encryptionConfig.ivLengthBytes)
        val ciphertext = encryptedBytes.copyOfRange(encryptionConfig.ivLengthBytes, encryptedBytes.size)

        val secretKey = SecretKeySpec(encryptionConfig.key, "AES")
        val cipher = Cipher.getInstance(encryptionConfig.algorithm)
        cipher.init(
            Cipher.DECRYPT_MODE,
            secretKey,
            GCMParameterSpec(encryptionConfig.tagLengthBits, iv)
        )
        return cipher.doFinal(ciphertext)
    }

    // ── Drive API helpers ────────────────────────────────────

    private fun fileName(entityName: String): String = "${folderName}_${entityName}.enc"

    private fun <T : Any> downloadAndDecryptMap(entityName: String): Map<String, T> {
        val bytes = downloadFile(fileName(entityName)) ?: return emptyMap()
        val decrypted = decrypt(bytes)
        return deserializeMap(entityName, decrypted)
    }

    private fun encryptAndUpload(entityName: String, plainBytes: ByteArray) {
        val encrypted = encrypt(plainBytes)
        uploadFile(fileName(entityName), encrypted)
    }

    private fun uploadFile(fileName: String, data: ByteArray) {
        val existingId = findFileId(fileName)
        val content = ByteArrayContent("application/octet-stream", data)

        if (existingId != null) {
            driveService.files().update(existingId, null, content).execute()
        } else {
            val metadata = File().apply {
                name = fileName
                parents = listOf("appDataFolder")
            }
            driveService.files().create(metadata, content)
                .setFields("id")
                .execute()
        }
    }

    private fun downloadFile(fileName: String): ByteArray? {
        val fileId = findFileId(fileName) ?: return null
        val outputStream = ByteArrayOutputStream()
        driveService.files().get(fileId).executeMediaAndDownloadTo(outputStream)
        return outputStream.toByteArray()
    }

    private fun findFileId(fileName: String): String? {
        val result = driveService.files().list()
            .setQ("name = '$fileName'")
            .setSpaces("appDataFolder")
            .setFields("files(id)")
            .execute()
        return result.files?.firstOrNull()?.id
    }

    private fun deleteFile(fileName: String) {
        val fileId = findFileId(fileName) ?: return
        driveService.files().delete(fileId).execute()
    }
}
