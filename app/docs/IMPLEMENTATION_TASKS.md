# WorkPlanner Implementation Tasks

## Phase 1: Project Setup

- [x] **1.1** Add dependencies to `gradle/libs.versions.toml` and `app/build.gradle.kts` — Compose, Room, Hilt, Navigation, KSP, Kotlin Serialization, WorkManager, Credential Manager, Google Drive API
- [x] **1.2** Create `WorkPlannerApp.kt` — `@HiltAndroidApp` Application class
- [x] **1.3** Create `MainActivity.kt` — single-activity, `setContent {}` with Compose theme
- [x] **1.4** Set up Material3 theme — `ui/theme/Color.kt`, `Type.kt`, `Theme.kt`

## Phase 2: Data Layer

- [x] **2.1** Create `data/entity/TaskEntity.kt` — `@Entity` + `@Serializable`
- [x] **2.2** Create `data/entity/CommentEntity.kt` — `@Entity` + `@Serializable`
- [x] **2.3** Create `data/model/Task.kt`, `TaskStatus.kt`, `TaskWithDetails.kt` — domain models
- [x] **2.4** Create `data/model/Comment.kt` — domain model
- [x] **2.5** Create `data/mapper/TaskMapper.kt` — `toDomain()` / `toEntity()` extensions
- [x] **2.6** Create `data/mapper/CommentMapper.kt` — `toDomain()` / `toEntity()` extensions
- [x] **2.7** Create `data/dao/TaskDao.kt` — plain Kotlin interface (no Room annotations)
- [x] **2.8** Create `data/dao/CommentDao.kt` — plain Kotlin interface
- [x] **2.9** Create `data/room/RoomTaskDao.kt` — extends TaskDao, Room annotations
- [x] **2.10** Create `data/room/RoomCommentDao.kt` — extends CommentDao, Room annotations
- [x] **2.11** Create `data/room/WorkPlannerDatabase.kt` — `@Database`, exposes Room DAOs
- [x] **2.12** Create `data/TaskRepository.kt` — wraps DAOs, maps to domain, hierarchy helpers

## Phase 3: Dependency Injection

- [ ] **3.1** Create `di/AppModule.kt` — provides Database, DAOs, TaskRepository

## Phase 4: Navigation

- [ ] **4.1** Create `ui/navigation/Screen.kt` — sealed class route definitions
- [ ] **4.2** Create `ui/navigation/NavGraph.kt` — NavHost + route wiring

## Phase 5: Task List Screen

- [ ] **5.1** Create `ui/tasklist/TaskListViewModel.kt` — state, tab switching, data loading
- [ ] **5.2** Create `ui/tasklist/TaskListScreen.kt` — 3-tab layout (Themes, Actionable, Search)
- [ ] **5.3** Create `ui/tasklist/components/TaskCard.kt` — reusable task card composable
- [ ] **5.4** Create `ui/tasklist/components/EmptyState.kt` — empty state composable
- [ ] **5.5** Create `ui/common/components/LoadingIndicator.kt`

## Phase 6: Task Detail Screen

- [ ] **6.1** Create `ui/taskdetail/TaskDetailViewModel.kt` — view/edit/create state, CRUD operations
- [ ] **6.2** Create `ui/taskdetail/TaskDetailScreen.kt` — view mode, edit mode, new task mode
- [ ] **6.3** Create `ui/taskdetail/components/TaskInfoSection.kt` — title, description, status, priority, due date
- [ ] **6.4** Create `ui/taskdetail/components/CommentSection.kt` — comment list + input
- [ ] **6.5** Create `ui/taskdetail/components/BreadcrumbBar.kt` — tappable hierarchy path
- [ ] **6.6** Create `ui/taskdetail/components/ParentPickerDialog.kt` — searchable parent selector

## Phase 7: Google Auth

- [ ] **7.1** Create `auth/GoogleAuthManager.kt` — Credential Manager API wrapper
- [ ] **7.2** Create `di/AuthModule.kt` — provides GoogleAuthManager
- [ ] **7.3** Create `ui/auth/AuthViewModel.kt` — sign-in, passphrase, restore state
- [ ] **7.4** Create `ui/auth/AuthScreen.kt` — sign-in, passphrase creation, passphrase entry

## Phase 8: KVStore + Backup

- [ ] **8.1** Create `generic/kvstore/EntityRegistration.kt` — PrimaryKeyConfig, IndexConfig, EntityRegistration
- [ ] **8.2** Create `generic/kvstore/EncryptionConfig.kt` — encryption settings data class
- [ ] **8.3** Create `generic/kvstore/KVStore.kt` — abstract base class
- [ ] **8.4** Create `backup/gdrive/GDriveKVStore.kt` — KVStore impl with encryption + Drive API
- [ ] **8.5** Create `backup/BackupProcessor.kt` — orchestrates Room ↔ KVStore sync
- [ ] **8.6** Create `backup/SyncWorker.kt` — WorkManager periodic sync (1 hour)
- [ ] **8.7** Create `di/BackupModule.kt` — provides KVStore, BackupProcessor

## Phase 9: Settings Screen

- [ ] **9.1** Create `ui/settings/SettingsViewModel.kt` — account info, sync controls
- [ ] **9.2** Create `ui/settings/SettingsScreen.kt` — account, backup, passphrase, sign out

## Phase 10: Final Wiring

- [ ] **10.1** Update `AndroidManifest.xml` — permissions (INTERNET), MainActivity, Application class
- [ ] **10.2** Wire start destination logic — Auth vs TaskList based on sign-in state

## Phase 11: Tests

- [ ] **11.1** Add test dependencies — JUnit, Turbine (Flow testing), Compose test, Room test
- [ ] **11.2** Create fake DAOs — `FakeTaskDao`, `FakeCommentDao` implementing plain interfaces
- [ ] **11.3** Unit tests — mappers (`TaskMapper`, `CommentMapper`)
- [ ] **11.4** Unit tests — `TaskRepository` (with fake DAOs)
- [ ] **11.5** Unit tests — `TaskListViewModel`
- [ ] **11.6** Unit tests — `TaskDetailViewModel`
- [ ] **11.7** Instrumented tests — Room DAO queries (in-memory DB)
- [ ] **11.8** Instrumented tests — Compose UI tests (screen rendering, navigation flows)
- [ ] **11.9** End-to-end test — create theme, add sub-tasks, add comments, close task, search
