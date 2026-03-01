# WorkPlanner Architecture

## Overview

WorkPlanner is a single-user Android app for organizing work into hierarchical tasks. Data is stored locally in a SQLite database (via Room) and backed up as encrypted JSON to Google Drive.

---

## Data Model

### Task Hierarchy

Tasks form an infinite tree structure:

```
Theme A (top-level)
  ├── Sub-task 1
  │     ├── Action item 1.1
  │     └── Action item 1.2
  └── Sub-task 2
        └── Action item 2.1
              └── Sub-action 2.1.1
Theme B (top-level)
  └── ...
```

- **Top-level tasks** (no parent) are "themes" — broad categories of work.
- **Bottom-level tasks** (no children) are "actionable items" — concrete things to do.
- **Middle tasks** are organizational groupings.
- There is no depth limit.

### Entities

#### tasks

| Column    | Type        | Notes                                      |
|-----------|-------------|--------------------------------------------|
| id        | TEXT (UUID)  | Primary key. UUID for sync-friendliness.  |
| parentId  | TEXT (UUID)? | FK → tasks.id. NULL = root/theme.         |
| title     | TEXT         | Required.                                  |
| description | TEXT       | Optional, defaults to "".                  |
| status    | TEXT         | "PENDING" or "CLOSED".                     |
| createdAt | INTEGER      | Epoch millis.                              |
| updatedAt | INTEGER      | Epoch millis.                              |

- `parentId` has a self-referencing foreign key with **CASCADE delete** — deleting a parent deletes all descendants automatically.
- Index on `parentId` for fast hierarchy queries.
- Ordering within siblings is by `createdAt ASC`.

#### comments

| Column    | Type        | Notes                                      |
|-----------|-------------|--------------------------------------------|
| id        | TEXT (UUID)  | Primary key.                              |
| taskId    | TEXT (UUID)  | FK → tasks.id, CASCADE delete.            |
| text      | TEXT         | Comment body.                              |
| createdAt | INTEGER      | Epoch millis.                              |
| updatedAt | INTEGER      | Epoch millis.                              |

- Index on `taskId`.
- Ordered by `createdAt DESC` (newest first).

### Why UUIDs?

Auto-increment IDs would collide when restoring a backup onto a device with existing data. UUIDs are globally unique and make JSON serialization clean.

---

## Local Storage (Room / SQLite)

Room is the local source of truth. All UI reads and writes go through Room.

```
App UI ←→ ViewModel ←→ Repository ←→ Room DAOs ←→ SQLite DB
```

- **DAOs** expose `Flow<List<T>>` for reactive UI updates.
- **Repository** wraps DAOs, provides domain model mapping, and handles hierarchy helpers (e.g., breadcrumb generation by walking up the `parentId` chain).
- The database file lives at the app's private internal storage (`/data/data/com.boxbuilder.workplanner/databases/workplanner.db`).

### Key Queries

| Operation              | Query                                                |
|------------------------|------------------------------------------------------|
| Get root themes        | `SELECT * FROM tasks WHERE parentId IS NULL ORDER BY createdAt` |
| Get children           | `SELECT * FROM tasks WHERE parentId = :id ORDER BY createdAt`   |
| Get child count        | `SELECT COUNT(*) FROM tasks WHERE parentId = :id`    |
| Get breadcrumbs        | Iterative: walk up `parentId` chain in Kotlin code   |
| Get all (for export)   | `SELECT * FROM tasks` / `SELECT * FROM comments`     |

---

## Google Authentication

Uses the **Credential Manager API** (modern replacement for legacy GoogleSignIn).

### Sign-In Flow

1. User taps "Sign in with Google" on AuthScreen.
2. Credential Manager presents Google account picker.
3. On success, we get a `GoogleIdTokenCredential` (contains user email, name, photo).
4. We store sign-in state in SharedPreferences.
5. For Drive API calls, we create a `GoogleAccountCredential` with `DriveScopes.DRIVE_APPDATA` scope.

### Required Scopes

- `openid` + `profile` + `email` — for sign-in identity.
- `drive.appdata` — read/write to the app's hidden Drive folder only. Least-privilege.

---

## Google Drive Sync

### Storage Location: AppData Folder

The AppData folder is a hidden, app-specific folder in the user's Google Drive:
- Only this app can read/write it.
- The user cannot see or accidentally delete it.
- Requires only the minimal `drive.appdata` scope.

### What Gets Stored on Drive

```
AppData/
  workplanner_backup.enc    ← Encrypted JSON of all tasks + comments
  encryption_salt.bin       ← PBKDF2 salt (not secret, safe to store unencrypted)
```

### Backup JSON Structure (before encryption)

```json
{
  "version": 1,
  "exportedAt": 1709312400000,
  "tasks": [
    {
      "id": "uuid-1",
      "parentId": null,
      "title": "Project Alpha",
      "description": "Main project theme",
      "status": "PENDING",
      "createdAt": 1709312400000,
      "updatedAt": 1709312400000
    }
  ],
  "comments": [
    {
      "id": "uuid-2",
      "taskId": "uuid-1",
      "text": "Started working on this",
      "createdAt": 1709312400000,
      "updatedAt": 1709312400000
    }
  ]
}
```

### Sync Schedule

- **Periodic**: WorkManager runs a sync worker every **1 hour**.
  - Requires network connectivity (constraint).
  - Uses `ExistingPeriodicWorkPolicy.KEEP` to avoid stacking.
- **Manual**: "Sync Now" button in Settings.
- **On app launch**: If last sync was >1 hour ago, trigger immediate sync.
- **On first sign-in**: Check Drive for existing backup → offer restore.

### Sync Worker Flow (Upload)

1. Verify signed in + encryption key exists in Android Keystore.
2. Query all tasks and comments from Room.
3. Serialize to JSON (`BackupData` model).
4. Encrypt JSON bytes with AES-256-GCM.
5. Upload encrypted blob to Drive AppData (replace previous backup).
6. Record `lastSyncTime` in SharedPreferences.

### Restore Flow (Download)

1. Download encrypted backup from Drive AppData.
2. Prompt user for passphrase (if key not in local Keystore).
3. Derive key from passphrase + salt (downloaded from Drive).
4. Decrypt → parse JSON.
5. Clear local Room DB.
6. Insert all tasks and comments from backup.

---

## Encryption

All data leaving the device is encrypted. Local Room DB stays plaintext (protected by Android's app sandbox).

### Algorithm

- **AES-256-GCM** — authenticated encryption (confidentiality + integrity).
- **PBKDF2WithHmacSHA256** — key derivation from passphrase.
  - 256-bit key output.
  - Random 16-byte salt.
  - 210,000 iterations (OWASP recommendation).

### Key Management

| Scenario | What Happens |
|----------|-------------|
| First install | User creates passphrase → derive key → store in Android Keystore → upload salt to Drive |
| Same device, returning | Key loaded from Android Keystore → no passphrase prompt |
| New device | Download salt from Drive → prompt passphrase → derive key → store in Keystore |
| Passphrase change | New salt + new key → re-encrypt backup → upload both |
| Forgotten passphrase | Backup is unrecoverable. Local data still works. |

### Encrypted File Format

```
[12-byte IV][AES-256-GCM ciphertext + 16-byte auth tag]
```

The IV (initialization vector) is randomly generated per encryption operation and prepended to the ciphertext. GCM's auth tag is appended automatically by the Java Crypto API.

### EncryptionManager (single class)

Responsibilities:
- `deriveKey(passphrase, salt) → SecretKey`
- `generateSalt() → ByteArray`
- `encrypt(plainBytes, key) → encryptedBytes` (generates random IV, prepends it)
- `decrypt(encryptedBytes, key) → plainBytes` (extracts IV, decrypts, verifies auth tag)

---

## App Architecture Layers

```
┌─────────────────────────────────────────┐
│                   UI                     │
│  (Compose Screens + Navigation)          │
├─────────────────────────────────────────┤
│              ViewModels                  │
│  (UI state, user action handlers)        │
├─────────────────────────────────────────┤
│             Repositories                 │
│  TaskRepository    SyncRepository        │
├──────────────┬──────────────────────────┤
│  Room DAOs   │  Drive + Encryption       │
│  (Local DB)  │  (Remote Backup)          │
└──────────────┴──────────────────────────┘
```

### Dependency Injection (Hilt)

- **AppModule**: Room database, DAOs.
- **RepositoryModule**: TaskRepository, SyncRepository bindings.
- **DriveModule**: GoogleAuthManager, EncryptionManager.

### Tech Stack

| Layer          | Technology                          |
|----------------|-------------------------------------|
| UI             | Jetpack Compose + Material3         |
| Navigation     | Compose Navigation                  |
| Local DB       | Room (SQLite)                       |
| DI             | Hilt                                |
| Auth           | Credential Manager API              |
| Drive          | Google Drive REST API (AppData)     |
| Serialization  | Kotlin Serialization (JSON)         |
| Background Sync| WorkManager (periodic, 1 hour)      |
| Encryption     | AES-256-GCM + PBKDF2 (Java Crypto) |
| Async          | Kotlin Coroutines + Flow            |

---

## First Launch Flow

```
App Launch
    │
    ▼
Signed in? ──No──► AuthScreen
    │                   │
   Yes              Sign In
    │                   │
    ▼                   ▼
Key in Keystore?   Backup on Drive?
    │                   │
   Yes              ┌──Yes──┐       No
    │                │       │       │
    ▼                ▼       │       ▼
 Normal Use    Prompt for    │   Prompt: Create
               passphrase    │   passphrase
                    │        │       │
                    ▼        │       ▼
               Decrypt &     │   Generate salt,
               restore DB    │   derive key,
                    │        │   store in Keystore,
                    ▼        │   upload salt to Drive
               Normal Use    │       │
                             │       ▼
                             │   Normal Use
                             │   (empty DB, first sync
                             │    will create backup)
                             │
                            No backup found
                             │
                             ▼
                         Prompt: Create
                         passphrase
                             │
                             ▼
                         Normal Use
```