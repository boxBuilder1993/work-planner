# WorkPlanner Package Structure

## Base Package

`com.boxbuilder.workplanner`

## Full Structure

```
com.boxbuilder.workplanner/
│
│── WorkPlannerApp.kt                        @HiltAndroidApp Application class
│── MainActivity.kt                          Single-activity, hosts Compose
│
├── generic/                                 Reusable abstractions (not app-specific)
│   └── kvstore/
│       ├── KVStore.kt                       Abstract base class (registration, validation)
│       ├── EntityRegistration.kt            PrimaryKeyConfig, IndexConfig, EntityRegistration
│       └── EncryptionConfig.kt              Encryption settings data class
│
├── data/                                    All data-related code
│   ├── entity/                              Room + Serializable annotated entities
│   │   ├── TaskEntity.kt                    @Entity + @Serializable
│   │   └── CommentEntity.kt                @Entity + @Serializable
│   ├── model/                               Domain models (UI layer works with these)
│   │   ├── Task.kt                          Domain task
│   │   ├── TaskStatus.kt                    Enum: PENDING, CLOSED
│   │   ├── TaskWithDetails.kt               Task + comments + child count
│   │   └── Comment.kt                       Domain comment
│   ├── dao/                                 DAO interfaces (plain Kotlin, no annotations)
│   │   ├── TaskDao.kt                       Task data operations interface
│   │   └── CommentDao.kt                    Comment data operations interface
│   ├── room/                                Room implementations of DAOs
│   │   ├── RoomTaskDao.kt                   @Dao, extends TaskDao, Room annotations
│   │   ├── RoomCommentDao.kt                @Dao, extends CommentDao, Room annotations
│   │   └── WorkPlannerDatabase.kt           @Database, exposes Room DAOs
│   ├── mapper/                              Entity ↔ domain model mapping
│   │   ├── TaskMapper.kt                    TaskEntity.toDomain(), Task.toEntity()
│   │   └── CommentMapper.kt                CommentEntity.toDomain(), Comment.toEntity()
│   └── TaskRepository.kt                   Single access point for all data operations
│
├── backup/                                  Backup and sync layer
│   ├── gdrive/                              Google Drive KVStore implementation
│   │   └── GDriveKVStore.kt                 Extends KVStore, handles encryption + Drive API
│   ├── BackupProcessor.kt                   Orchestrates Room ↔ KVStore sync
│   └── SyncWorker.kt                        WorkManager periodic sync worker
│
├── ui/                                      All UI code (Jetpack Compose)
│   ├── theme/                               Material3 theme
│   │   ├── Color.kt
│   │   ├── Type.kt
│   │   └── Theme.kt
│   ├── navigation/                          Compose Navigation
│   │   ├── Screen.kt                        Route definitions (sealed class)
│   │   └── NavGraph.kt                      NavHost + route wiring
│   ├── auth/                                Google Sign-In screen
│   │   ├── AuthScreen.kt
│   │   └── AuthViewModel.kt
│   ├── tasklist/                            Task list (root themes or children)
│   │   ├── TaskListScreen.kt
│   │   ├── TaskListViewModel.kt
│   │   └── components/
│   │       ├── TaskCard.kt
│   │       ├── BreadcrumbBar.kt
│   │       └── EmptyState.kt
│   ├── taskdetail/                          Task detail view
│   │   ├── TaskDetailScreen.kt
│   │   ├── TaskDetailViewModel.kt
│   │   └── components/
│   │       ├── TaskInfoSection.kt
│   │       └── CommentSection.kt
│   ├── taskedit/                            Create / edit task form
│   │   ├── TaskEditScreen.kt
│   │   └── TaskEditViewModel.kt
│   ├── settings/                            Sync controls, account management
│   │   ├── SettingsScreen.kt
│   │   └── SettingsViewModel.kt
│   └── common/                              Shared UI components
│       └── components/
│           ├── LoadingIndicator.kt
│           └── ConfirmDeleteDialog.kt
│
├── auth/                                    Google auth management
│   └── GoogleAuthManager.kt                 Credential Manager API wrapper
│
└── di/                                      Hilt dependency injection modules
    ├── AppModule.kt                         Database, DAOs, Repository
    ├── BackupModule.kt                      KVStore, BackupProcessor
    └── AuthModule.kt                        GoogleAuthManager
```

## Design Principles

### Package = purpose
The package name tells you what the class is. Files are grouped by what they do, not what pattern they follow.

### Suffixes for disambiguation
Class names use suffixes only where needed to avoid import collisions:
- `TaskEntity` vs `Task` — entity vs domain model
- `RoomTaskDao` vs `TaskDao` — implementation vs interface
- `TaskMapper` — clear purpose

### Layer boundaries

```
ui/          → only imports from data/model/, data/TaskRepository
data/        → entity/, model/, dao/, room/, mapper/ are internal concerns
               TaskRepository is the public API
backup/      → imports from data/dao/, data/entity/, generic/kvstore/
generic/     → imports nothing from the app (fully reusable)
di/          → wires everything together
auth/        → standalone, used by ui/auth/ and backup/
```

### Adding a new entity type

To add a new entity (e.g., tags):
1. `data/entity/TagEntity.kt` — @Entity + @Serializable
2. `data/model/Tag.kt` — domain model
3. `data/dao/TagDao.kt` — plain interface
4. `data/room/RoomTagDao.kt` — Room implementation
5. `data/mapper/TagMapper.kt` — entity ↔ domain
6. Update `data/room/WorkPlannerDatabase.kt` — add to @Database entities + DAO
7. Update `data/TaskRepository.kt` — or create `TagRepository.kt` if independent
8. Update `backup/BackupProcessor.kt` — register entity with KVStore
9. Update `di/AppModule.kt` — provide new DAO

### Adding a new screen

To add a new screen (e.g., search):
1. Create `ui/search/` package
2. `SearchScreen.kt` — composable
3. `SearchViewModel.kt` — state + actions
4. Add route to `ui/navigation/Screen.kt`
5. Add composable to `ui/navigation/NavGraph.kt`
