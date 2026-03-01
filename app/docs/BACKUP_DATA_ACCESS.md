# WorkPlanner Data Access Layer

## Overview

The data access layer has two independent systems connected by a BackupProcessor:

```
┌──────────────────────────────────────────────────────┐
│                    TaskRepository                     │
│              (app reads/writes here)                  │
├──────────────┬───────────────────────────────────────┤
│              │                                        │
│   Room DB    │          BackupProcessor               │
│  (SQLite)    │     (Room ↔ KV Store sync)             │
│  Local,      │              │                         │
│  source of   │          KVStore                       │
│  truth       │     (abstract class)                   │
│              │   registration + validation            │
│              │              │                         │
│              │       GDriveKVStore                    │
│              │  (encryption + Drive + serialization)  │
└──────────────┴───────────────────────────────────────┘
```

- **Room DB** — local SQLite database. Source of truth. All UI reads/writes go here.
- **KVStore** — abstract base class. Handles entity registration, PK extraction, index extraction, and validation. Says nothing about encryption, serialization, or backends.
- **GDriveKVStore** — extends KVStore. Implements actual storage using Google Drive. Internally handles encryption, Kotlin serialization, and Drive API calls.
- **BackupProcessor** — orchestrator. Reads from Room, writes to KV store (backup). Reads from KV store, writes to Room (restore). Only talks to the `KVStore` type.

---

## Entity Registration

Every entity type must be registered before use. Registration provides the store with everything it needs to identify and index entities. Entity classes must be annotated with `@Serializable` — serialization is enforced at runtime by backends that need it (e.g., GDriveKVStore calls `serializer<T>()` which throws if the annotation is missing).

### Registration Model

```kotlin
data class PrimaryKeyConfig<T>(
    val componentNames: List<String>,            // declared key fields: ["id"]
    val extractor: (T) -> Map<String, String>    // must return exactly these keys
)

data class IndexConfig<T>(
    val indexName: String,                       // e.g., "parentId_index"
    val componentNames: List<String>,            // declared component fields: ["parentId"]
    val extractor: (T) -> Map<String, String>    // must return exactly these keys
)

data class EntityRegistration<T>(
    val primaryKey: PrimaryKeyConfig<T>,
    val indexes: List<IndexConfig<T>>
)
```

### Serialization

Serialization is **not** part of the registration — it's a backend concern.

- The `KVStore` base class and `EntityRegistration` know nothing about serialization.
- Each backend handles serialization in its own way.
- `GDriveKVStore` uses Kotlin Serialization. It **validates at registration time** (via `registerEntity` override) that the entity class is `@Serializable` by attempting to obtain its serializer. If the annotation is missing, registration fails immediately — no silent failures later during save/get.
- A future backend (e.g., DynamoDB) might use a different serialization strategy and validate for its own requirements at registration time.

```kotlin
@Serializable  // Required — GDriveKVStore validates this at registration time
data class TaskEntity(
    val id: String,
    val parentId: String?,
    val title: String,
    // ...
)
```

### Registration Examples

```kotlin
kvStore.registerEntity("tasks", EntityRegistration(
    primaryKey = PrimaryKeyConfig(
        componentNames = listOf("id"),
        extractor = { mapOf("id" to it.id) }
    ),
    indexes = listOf(
        IndexConfig(
            indexName = "parentId_index",
            componentNames = listOf("parentId"),
            extractor = { mapOf("parentId" to (it.parentId ?: "null")) }
        ),
        IndexConfig(
            indexName = "status_index",
            componentNames = listOf("status"),
            extractor = { mapOf("status" to it.status) }
        )
    )
))

kvStore.registerEntity("comments", EntityRegistration(
    primaryKey = PrimaryKeyConfig(
        componentNames = listOf("id"),
        extractor = { mapOf("id" to it.id) }
    ),
    indexes = listOf(
        IndexConfig(
            indexName = "taskId_index",
            componentNames = listOf("taskId"),
            extractor = { mapOf("taskId" to it.taskId) }
        )
    )
))
```

### Validation

The base `KVStore` class validates extractors against declared component names at runtime. If an extractor returns keys that don't match the declared `componentNames`, the store fails fast:

```
PrimaryKeyConfig(componentNames = ["id"], extractor returns {"id": "..."})             ✓ OK
PrimaryKeyConfig(componentNames = ["id"], extractor returns {"key": "..."})            ✗ FAIL: expected {id}, got {key}
IndexConfig(componentNames = ["parentId"], extractor returns {"status": "..."})        ✗ FAIL: expected {parentId}, got {status}
```

Validation also applies to `getByIndex` queries — the queried keys must match the index's declared components:

```kotlin
kvStore.getByIndex("tasks", "parentId_index", mapOf("parentId" to "uuid-1"))  // ✓ OK
kvStore.getByIndex("tasks", "parentId_index", mapOf("status" to "PENDING"))   // ✗ FAIL
```

---

## KVStore (Abstract Base Class)

Handles entity registration, validation, PK/index extraction. Subclasses only implement actual storage operations.

```kotlin
abstract class KVStore {

    // ── Registry ──────────────────────────────────────────────

    private val registry = mutableMapOf<String, EntityRegistration<*>>()

    open fun <T : Any> registerEntity(entityName: String, registration: EntityRegistration<T>) {
        require(entityName.isNotBlank()) { "Entity name cannot be blank" }
        require(registration.primaryKey.componentNames.isNotEmpty()) {
            "Primary key must have at least one component"
        }
        registration.indexes.forEach { index ->
            require(index.componentNames.isNotEmpty()) {
                "Index '${index.indexName}' must have at least one component"
            }
        }
        registry[entityName] = registration
    }

    // ── Protected helpers for subclasses ──────────────────────

    protected fun <T : Any> getRegistration(entityName: String): EntityRegistration<T> {
        @Suppress("UNCHECKED_CAST")
        return registry[entityName] as? EntityRegistration<T>
            ?: throw IllegalStateException("Entity '$entityName' not registered")
    }

    protected fun <T : Any> extractPrimaryKey(entityName: String, value: T): Map<String, String> {
        val reg = getRegistration<T>(entityName)
        val extracted = reg.primaryKey.extractor(value)
        validateKeys(
            reg.primaryKey.componentNames, extracted.keys, "PrimaryKey of '$entityName'"
        )
        return extracted
    }

    protected fun <T : Any> extractIndexValues(
        entityName: String, indexName: String, value: T
    ): Map<String, String> {
        val index = findIndex<T>(entityName, indexName)
        val extracted = index.extractor(value)
        validateKeys(
            index.componentNames, extracted.keys, "Index '$indexName' on '$entityName'"
        )
        return extracted
    }

    protected fun validateQueryKeys(
        entityName: String, indexName: String, queryKeys: Set<String>
    ) {
        val index = findIndex<Any>(entityName, indexName)
        validateKeys(index.componentNames, queryKeys, "Query on index '$indexName'")
    }

    // Derive a storage key string from PK map (joined in declared component order)
    protected fun <T : Any> deriveStorageKey(entityName: String, value: T): String {
        val reg = getRegistration<T>(entityName)
        val pkMap = extractPrimaryKey(entityName, value)
        return reg.primaryKey.componentNames.joinToString("#") { pkMap[it]!! }
    }

    // ── Private helpers ───────────────────────────────────────

    private fun <T : Any> findIndex(entityName: String, indexName: String): IndexConfig<T> {
        val reg = getRegistration<T>(entityName)
        return reg.indexes.find { it.indexName == indexName }
            ?: throw IllegalStateException("Index '$indexName' not found on entity '$entityName'")
    }

    private fun validateKeys(expected: List<String>, actual: Set<String>, context: String) {
        val expectedSet = expected.toSet()
        if (actual != expectedSet) {
            throw IllegalStateException(
                "$context: expected keys $expectedSet but extractor returned $actual"
            )
        }
    }

    // ── Abstract methods (implemented by each backend) ────────

    abstract suspend fun <T : Any> save(entity: String, value: T)
    abstract suspend fun <T : Any> saveAll(entity: String, values: List<T>)
    abstract suspend fun <T : Any> get(entity: String, id: String): T?
    abstract suspend fun <T : Any> getAll(entity: String): List<T>
    abstract suspend fun <T : Any> getByIndex(
        entity: String,
        indexName: String,
        indexValues: Map<String, String>
    ): List<T>
    abstract suspend fun delete(entity: String, id: String)
    abstract suspend fun deleteAll(entity: String)
    abstract suspend fun exists(entity: String): Boolean
}
```

### What the base class provides vs. what subclasses implement

| Concern                       | Base class (KVStore)   | Subclass (e.g., GDriveKVStore)  |
|-------------------------------|------------------------|---------------------------------|
| Entity registry               | Manages                | Uses via `getRegistration()`    |
| PK extraction + validation    | Provides               | Calls `extractPrimaryKey()`     |
| Index extraction + validation | Provides               | Calls `extractIndexValues()`    |
| Query key validation          | Provides               | Calls `validateQueryKeys()`     |
| Storage key derivation        | Provides               | Calls `deriveStorageKey()`      |
| Registration validation       | Handles                | —                               |
| Serialization                 | —                      | Backend-specific                |
| Encryption                    | —                      | Backend-specific                |
| Actual storage I/O            | —                      | Backend-specific                |

---

## GDriveKVStore

Extends `KVStore`. Implements actual storage using Google Drive AppData folder. Handles encryption and serialization internally.

### Constructor

```kotlin
class GDriveKVStore(
    private val driveService: Drive,
    private val encryptionConfig: EncryptionConfig,
    private val folderName: String
) : KVStore() {

    // Cached serializers, populated at registration time
    private val serializers = mutableMapOf<String, KSerializer<*>>()

    override fun <T : Any> registerEntity(entityName: String, registration: EntityRegistration<T>) {
        // Base class handles registry + PK/index validation
        super.registerEntity(entityName, registration)

        // GDrive-specific: verify entity is @Serializable and cache serializer
        try {
            val serializer = serializer(registration.primaryKey.extractor::class.java /* T's class */)
            serializers[entityName] = serializer
        } catch (e: SerializationException) {
            throw IllegalArgumentException(
                "Entity '$entityName' must be @Serializable for GDriveKVStore", e
            )
        }
    }
}
```

### EncryptionConfig

```kotlin
data class EncryptionConfig(
    val key: SecretKey,
    val algorithm: String = "AES/GCM/NoPadding",
    val keyDerivation: String = "PBKDF2WithHmacSHA256",
    val ivLengthBytes: Int = 12,
    val tagLengthBits: Int = 128
)
```

### Serialization

`GDriveKVStore` uses Kotlin Serialization internally. Serializers are validated and cached at registration time (see `registerEntity` override above). At save/get time, the cached serializer is used — no runtime discovery needed.

```kotlin
// Inside GDriveKVStore method implementations:
private fun <T : Any> serialize(entityName: String, value: T): ByteArray {
    @Suppress("UNCHECKED_CAST")
    val serializer = serializers[entityName] as KSerializer<T>
    return Json.encodeToString(serializer, value).toByteArray()
}

private fun <T : Any> deserialize(entityName: String, bytes: ByteArray): T {
    @Suppress("UNCHECKED_CAST")
    val serializer = serializers[entityName] as KSerializer<T>
    return Json.decodeFromString(serializer, String(bytes))
}
```

If an entity is not `@Serializable`, registration fails immediately — save/get never encounters a missing serializer.

### Storage Layout on Drive

```
AppData/
  {folderName}/
    tasks.enc                      ← All task entries, encrypted
    comments.enc                   ← All comment entries, encrypted
    _meta/
      salt.bin                     ← PBKDF2 salt (unencrypted, not secret)
```

Each `.enc` file contains the encrypted form of a JSON map: `{ "pk1": {entity1}, "pk2": {entity2}, ... }`. The entire map is serialized → encrypted → uploaded as one blob.

**Why bulk blobs (not one file per entity)?**
- Drive API has per-request overhead. Individual files per entry = too many API calls.
- Total data volume for a task planner is small (KBs to low MBs).
- `getAll()` is the primary access pattern during backup/restore.

### Internal Flow (save)

```
save("tasks", taskObj)
    │
    ▼
1. Base class: extractPrimaryKey → {"id": "uuid-1"} (validated)
   Base class: deriveStorageKey  → "uuid-1"
    │
    ▼
2. Serialize taskObj → JSON string (via Kotlin Serialization)
    │
    ▼
3. Download existing tasks.enc from Drive (if exists)
    │
    ▼
4. Decrypt → deserialize to Map<String, JsonElement>
    │
    ▼
5. Add/update entry:  map["uuid-1"] = serialized JSON
    │
    ▼
6. Serialize full map → encrypt → upload as tasks.enc
```

### Internal Flow (getAll)

```
getAll("tasks")
    │
    ▼
1. Download tasks.enc from Drive
    │
    ▼
2. Decrypt → JSON bytes
    │
    ▼
3. Deserialize JSON map, each value deserialized via Kotlin Serialization
    │
    ▼
4. Return List<T> of all values
```

### Internal Flow (getByIndex)

```
getByIndex("tasks", "parentId_index", mapOf("parentId" to "uuid-123"))
    │
    ▼
1. Base class: validateQueryKeys → confirms {"parentId"} matches index declaration ✓
    │
    ▼
2. getAll("tasks")              ← downloads + decrypts everything
    │
    ▼
3. For each entity:
     Base class: extractIndexValues("tasks", "parentId_index", entity)
       → {"parentId": "uuid-456"} (validated)
     Check if extracted == queried values → no match
    │
    ▼
4. Return matching List<T>
```

Index filtering is done in-memory after decryption. This is acceptable for GDrive's bulk access pattern. A future `KVStore` subclass (e.g., backed by DynamoDB) could use `componentNames` from the registration to create native indexes and query them directly, skipping in-memory filtering.

---

## BackupProcessor

Orchestrates sync between Room DB and the KVStore. The only class that knows about both Room and the KV store. Talks to `KVStore` base type — does not know about GDrive, encryption, or serialization.

### Constructor

```kotlin
class BackupProcessor(
    private val taskDao: TaskDao,
    private val commentDao: CommentDao,
    private val kvStore: KVStore
) {
    init {
        kvStore.registerEntity("tasks", EntityRegistration(
            primaryKey = PrimaryKeyConfig(
                componentNames = listOf("id"),
                extractor = { mapOf("id" to it.id) }
            ),
            indexes = listOf(
                IndexConfig("parentId_index", listOf("parentId")) {
                    mapOf("parentId" to (it.parentId ?: "null"))
                },
                IndexConfig("status_index", listOf("status")) {
                    mapOf("status" to it.status)
                }
            )
        ))

        kvStore.registerEntity("comments", EntityRegistration(
            primaryKey = PrimaryKeyConfig(
                componentNames = listOf("id"),
                extractor = { mapOf("id" to it.id) }
            ),
            indexes = listOf(
                IndexConfig("taskId_index", listOf("taskId")) {
                    mapOf("taskId" to it.taskId)
                }
            )
        ))
    }
}
```

### API

```kotlin
// Backup: Room → KV Store
suspend fun performBackup()

// Restore: KV Store → Room
suspend fun performRestore(): Boolean   // returns true if backup was found

// Check if remote backup exists
suspend fun hasRemoteBackup(): Boolean
```

### Backup Flow

```
1. taskDao.getAllTasks()           → List<TaskEntity>
2. commentDao.getAllComments()     → List<CommentEntity>
3. kvStore.saveAll("tasks", tasks)          ← PKs extracted automatically by base class
4. kvStore.saveAll("comments", comments)
5. Record lastSyncTime in SharedPreferences
```

### Restore Flow

```
1. kvStore.getAll("tasks")        → List<TaskEntity>
2. kvStore.getAll("comments")     → List<CommentEntity>
3. taskDao.deleteAllTasks()       → clear local DB (CASCADE handles comments)
4. taskDao.insertTasks(tasks)     → populate from backup
5. commentDao.insertComments(comments)
```

### Sync Schedule

- **Periodic**: WorkManager every 1 hour (requires network).
- **Manual**: "Sync Now" from Settings screen.
- **On app launch**: If last sync > 1 hour ago, trigger sync.

---

## Encryption

Encryption is handled entirely within `GDriveKVStore`. The `KVStore` base class and `BackupProcessor` know nothing about it.

See [ARCHITECTURE.md](ARCHITECTURE.md) for full encryption spec:
- **AES-256-GCM** — authenticated encryption (confidentiality + integrity).
- **PBKDF2WithHmacSHA256** — key derivation from user passphrase.
- Key cached in **Android Keystore** locally.
- **Salt** stored in Drive AppData (not secret).
- Encrypted file format: `[12-byte IV][ciphertext + 16-byte auth tag]`

---

## Room DB Schema

See [ARCHITECTURE.md](ARCHITECTURE.md) for full entity definitions and DAO queries.

Summary:
- **tasks**: id, parentId, title, description, status (PENDING/CLOSED), createdAt, updatedAt
- **comments**: id, taskId, text, createdAt, updatedAt
- Self-referencing FK on tasks.parentId with CASCADE delete.
- DAOs expose `Flow<List<T>>` for reactive UI updates.

---

## Swapping the KVStore Backend

To replace GDrive with another storage:

1. Create a new `KVStore` subclass (e.g., `S3KVStore`, `FirebaseKVStore`).
2. That subclass handles its own encryption, serialization, and storage internals.
3. Entity registration, PK/index validation are inherited from the base class for free.
4. Swap the binding in Hilt's DI module.
5. `BackupProcessor`, Room, and UI remain unchanged.

```kotlin
// Today
@Provides
@Singleton
fun provideKVStore(driveService: Drive, encryptionConfig: EncryptionConfig): KVStore {
    return GDriveKVStore(driveService, encryptionConfig, folderName = "workplanner")
}

// Tomorrow
@Provides
@Singleton
fun provideKVStore(s3Client: S3Client, encryptionConfig: EncryptionConfig): KVStore {
    return S3KVStore(s3Client, encryptionConfig, bucketName = "workplanner")
}
```