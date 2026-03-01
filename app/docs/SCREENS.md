# WorkPlanner Screen Designs

## Screen Overview

4 screens total:

| Screen           | Route                      | Purpose                                    |
|------------------|----------------------------|--------------------------------------------|
| AuthScreen       | `auth`                     | Google Sign-In + passphrase setup/entry     |
| TaskListScreen   | `tasklist`                 | Three tabs: Themes, Actionable, Search. Filters out CLOSED. |
| TaskDetailScreen | `taskdetail/{taskId}`      | View/edit task, sub-tasks, comments         |
| SettingsScreen   | `settings`                 | Account, sync, passphrase management        |

### Navigation Flow

```
AuthScreen → TaskListScreen (start destination after sign-in)
                │
                ├── Tap task card → TaskDetailScreen
                │                       │
                │                       ├── Tap sub-task → TaskDetailScreen (drill down)
                │                       ├── Add Child → TaskDetailScreen (new, blank)
                │                       └── Back ← previous screen
                │
                └── Settings icon → SettingsScreen
```

---

## Screen 1: AuthScreen

### Route: `auth`

First screen when not signed in. Handles Google Sign-In, passphrase creation (first time), and passphrase entry + restore (returning user on new device).

### States

**State 1: Sign-In**
```
┌──────────────────────────────┐
│                              │
│                              │
│                              │
│         WorkPlanner          │
│                              │
│   [ Sign in with Google ]    │
│                              │
│                              │
│                              │
└──────────────────────────────┘
```

**State 2: First time (no backup on Drive)**
```
┌──────────────────────────────┐
│                              │
│   Create a backup passphrase │
│                              │
│   This passphrase encrypts   │
│   your data on Google Drive. │
│   You'll need it to restore  │
│   on a new device.           │
│                              │
│   Passphrase:                │
│   ┌────────────────────────┐ │
│   │ ••••••••               │ │
│   └────────────────────────┘ │
│   Confirm:                   │
│   ┌────────────────────────┐ │
│   │ ••••••••               │ │
│   └────────────────────────┘ │
│                              │
│   ⚠ If you forget this,     │
│     your backup cannot be    │
│     recovered.               │
│                              │
│   [ Continue ]               │
│                              │
└──────────────────────────────┘
```

**State 3: Returning user (backup found on Drive)**
```
┌──────────────────────────────┐
│                              │
│   Backup found on Drive      │
│                              │
│   Enter your passphrase to   │
│   restore your data:         │
│                              │
│   Passphrase:                │
│   ┌────────────────────────┐ │
│   │ ••••••••               │ │
│   └────────────────────────┘ │
│                              │
│   [ Restore ]   [ Skip ]    │
│                              │
│   Wrong passphrase? ← error │
│                              │
└──────────────────────────────┘
```

### Behavior
- Sign-in via Credential Manager API
- After sign-in: check Drive AppData for existing backup
- If backup exists → State 3 (passphrase entry + restore)
- If no backup → State 2 (create passphrase)
- "Skip" on State 3 → go to TaskListScreen with empty local DB (doesn't restore, but still sets up passphrase for future backups — or prompt passphrase creation)
- On successful passphrase → derive key, store in Keystore, navigate to TaskListScreen

---

## Screen 2: TaskListScreen

### Route: `tasklist`

The main screen. Three tabs showing different views of the task tree. **All tabs filter out CLOSED tasks** — only PENDING tasks are shown.

### Layout

```
┌──────────────────────────────────────┐
│  WorkPlanner                     ⚙️  │
├──────────────────────────────────────┤
│  [ Themes ] [ Actionable ] [ Search ]│  ← tab bar
├──────────────────────────────────────┤
│                                      │
│  (tab content below)                 │
│                                      │
└──────────────────────────────────────┘
```

### Tab 1: Themes

Shows all root-level PENDING tasks (`parentId IS NULL AND status = 'PENDING'`). High-level categories.

```
┌──────────────────────────────────────┐
│  WorkPlanner                     ⚙️  │
├──────────────────────────────────────┤
│  [•Themes ] [ Actionable ] [ Search ]│
├──────────────────────────────────────┤
│ ┌──────────────────────────────────┐ │
│ │ Project Alpha                 ●  │ │
│ │ Main project for Q1              │ │
│ │ 5 sub-tasks                      │ │
│ └──────────────────────────────────┘ │
│ ┌──────────────────────────────────┐ │
│ │ Personal Tasks                ●  │ │
│ │ Non-work items                   │ │
│ │ 3 sub-tasks                      │ │
│ └──────────────────────────────────┘ │
│                                      │
│                                  [+] │  ← FAB: create new theme
└──────────────────────────────────────┘
```

**Task card contents:**
- Title
- Description (first line, truncated)
- Sub-task count

**Interactions:**
- Tap card → navigate to TaskDetailScreen for that task
- FAB → navigate to TaskDetailScreen with blank fields (new root task)
- Settings icon → SettingsScreen

### Tab 2: Actionable

Shows all PENDING leaf tasks across the entire tree — tasks that have zero children and are not CLOSED. Sorted by priority (1 first), then due date (latest first, null last).

```
┌──────────────────────────────────────┐
│  WorkPlanner                     ⚙️  │
├──────────────────────────────────────┤
│  [ Themes ] [•Actionable ] [ Search ]│
├──────────────────────────────────────┤
│ ┌──────────────────────────────────┐ │
│ ┌──────────────────────────────────┐ │
│ │ Write API spec           [1] ●  │ │  ← 1 = red badge
│ │ Project Alpha > Backend         │ │
│ │ Due: Mar 15                     │ │
│ └──────────────────────────────────┘ │
│ ┌──────────────────────────────────┐ │
│ │ Review PR #42            [2] ●  │ │
│ │ Project Alpha > Frontend        │ │
│ │ Due: Mar 10                     │ │
│ └──────────────────────────────────┘ │
│ ┌──────────────────────────────────┐ │
│ │ Buy groceries            [3] ●  │ │
│ │ Personal Tasks                  │ │
│ └──────────────────────────────────┘ │
│                                      │
│                                      │
└──────────────────────────────────────┘
```

**Task card contents:**
- Title
- Priority badge (colored number: 1=red, 2=orange, 3=yellow, 4=green, 5=blue)
- Hierarchy path (parent chain, truncated) — gives context
- Due date (if set)
- No FAB (actionable tasks created from a parent's detail screen)

### Tab 3: Search

Free-text search across all tasks (including CLOSED). Matches against title and description.

```
┌──────────────────────────────────────┐
│  WorkPlanner                     ⚙️  │
├──────────────────────────────────────┤
│  [ Themes ] [ Actionable ] [•Search ]│
├──────────────────────────────────────┤
│ ┌────────────────────────────────┐   │
│ │ 🔍 Search tasks...             │   │  ← search input
│ └────────────────────────────────┘   │
│                                      │
│ ┌──────────────────────────────────┐ │
│ │ Write API spec              ●    │ │
│ │ Project Alpha > Backend          │ │
│ └──────────────────────────────────┘ │
│ ┌──────────────────────────────────┐ │
│ │ API review meeting          ✓    │ │  ← CLOSED tasks show too
│ │ Project Alpha > Meetings         │ │
│ └──────────────────────────────────┘ │
│                                      │
│                                      │
└──────────────────────────────────────┘
```

**Search behavior:**
- Searches title and description fields
- Case-insensitive
- Shows results as they type (debounced)
- Shows ALL tasks (both PENDING and CLOSED) — this is the only place to find CLOSED tasks
- Each result shows hierarchy path and status indicator
- Tap result → TaskDetailScreen

**Empty state (no query):**
```
┌──────────────────────────────────────┐
│                                      │
│ ┌────────────────────────────────┐   │
│ │ 🔍 Search tasks...             │   │
│ └────────────────────────────────┘   │
│                                      │
│      Search across all tasks         │
│      by title or description         │
│                                      │
└──────────────────────────────────────┘
```

**Empty state (no results):**
```
┌──────────────────────────────────────┐
│                                      │
│ ┌────────────────────────────────┐   │
│ │ 🔍 some query                  │   │
│ └────────────────────────────────┘   │
│                                      │
│      No tasks found                  │
│                                      │
└──────────────────────────────────────┘
```

### Empty States

**Themes tab (no tasks):**
```
┌──────────────────────────────────────┐
│                                      │
│        No themes yet                 │
│                                      │
│   Tap + to create your               │
│   first theme                        │
│                                      │
│                                  [+] │
└──────────────────────────────────────┘
```

**Actionable tab (no leaf tasks):**
```
┌──────────────────────────────────────┐
│                                      │
│     No actionable tasks              │
│                                      │
│   Actionable tasks are               │
│   leaf-level tasks with              │
│   no sub-tasks.                      │
│                                      │
└──────────────────────────────────────┘
```

### DAO Support Needed

**Actionable tab** — get all PENDING leaf tasks (no children):

```sql
SELECT * FROM tasks
WHERE status = 'PENDING'
AND id NOT IN (SELECT DISTINCT parentId FROM tasks WHERE parentId IS NOT NULL)
ORDER BY priority ASC, CASE WHEN dueDate IS NULL THEN 1 ELSE 0 END, dueDate DESC
```

**Themes tab** — get PENDING root tasks:

```sql
SELECT * FROM tasks
WHERE parentId IS NULL AND status = 'PENDING'
ORDER BY createdAt ASC
```

**Search tab** — search all tasks by title/description:

```sql
SELECT * FROM tasks
WHERE title LIKE '%' || :query || '%'
   OR description LIKE '%' || :query || '%'
ORDER BY createdAt ASC
```

These need to be added to TaskDao / RoomTaskDao.

---

## Screen 3: TaskDetailScreen

### Route: `taskdetail/{taskId}` (or `taskdetail/new?parentId={parentId}` for creating)

The combined view/edit screen. Shows full task details, sub-tasks, and comments. Fields are read-only by default; an Edit button switches to edit mode.

### Layout (View Mode)

```
┌──────────────────────────────┐
│ ←                       ✏️  │  ← edit button
├──────────────────────────────┤
│ Root > Theme A > Sub-task 1  │  ← breadcrumb bar (tappable)
├──────────────────────────────┤
│                              │
│ Action item 1.1              │  ← title (read-only)
│                              │
│ This task involves writing   │  ← description (read-only)
│ the API specification for    │
│ the new endpoint.            │
│                              │
│ Status: ● PENDING            │
│ Priority: [3]                │  ← colored badge (1=red → 5=blue)
│ Due: Mar 15, 2026            │  ← or "No due date"
│                              │
│ ── Sub-tasks (3) ──────────  │
│ ┌────────────────────────┐   │
│ │ Define schema       ●  │   │  ← tap → navigate to its detail
│ └────────────────────────┘   │
│ ┌────────────────────────┐   │
│ │ Write examples      ✓  │   │
│ └────────────────────────┘   │
│ ┌────────────────────────┐   │
│ │ Get review          ●  │   │
│ └────────────────────────┘   │
│ [ + Add Child ]              │  ← creates new child task
│                              │
│ ── Comments ───────────────  │
│ ┌────────────────────────┐   │
│ │ Started working on     │   │
│ │ this today             │   │
│ │           Mar 1, 2026  │   │
│ └────────────────────────┘   │
│ ┌────────────────────────┐   │
│ │ Need to check with     │   │
│ │ team first             │   │
│ │           Feb 28, 2026 │   │
│ └────────────────────────┘   │
│                              │
│ ┌────────────────────┐ [→]  │  ← comment input + send
│ │ Add a comment...   │       │
│ └────────────────────┘       │
└──────────────────────────────┘
```

### Layout (Edit Mode — after tapping ✏️)

```
┌──────────────────────────────┐
│ ←              [Save] [Cancel]│
├──────────────────────────────┤
│ Root > Theme A > Sub-task 1  │
├──────────────────────────────┤
│                              │
│ Title:                       │
│ ┌────────────────────────┐   │
│ │ Action item 1.1        │   │  ← editable text field
│ └────────────────────────┘   │
│                              │
│ Description:                 │
│ ┌────────────────────────┐   │
│ │ This task involves     │   │  ← editable multiline field
│ │ writing the API spec   │   │
│ │ for the new endpoint.  │   │
│ └────────────────────────┘   │
│                              │
│ Status: [ PENDING ▼ ]       │  ← dropdown toggle
│                              │
│ Priority: [ 3 ▼ ]           │  ← dropdown (1-5)
│                              │
│ Due date:                    │
│ [ Mar 15, 2026    📅 ] [✕]  │  ← date picker + clear
│                              │
│ Parent:                      │
│ [ Theme A              ▼ ]  │  ← parent picker (tap to change)
│                              │
│ ── Sub-tasks (3) ──────────  │
│   (same as view mode)        │
│                              │
│ ── Comments ───────────────  │
│   (same as view mode)        │
│                              │
└──────────────────────────────┘
```

**Parent picker** — shows a searchable dialog/bottom-sheet listing all tasks. Selecting a new parent re-parents the task (moves it under a different parent). Selecting "None" makes it a root-level theme. A task cannot be re-parented to itself or any of its own descendants.

### Layout (New Task — via Add Child or FAB)

```
┌──────────────────────────────┐
│ ←              [Save] [Cancel]│
├──────────────────────────────┤
│ Root > Theme A > Sub-task 1  │  ← parent's breadcrumb + "New"
├──────────────────────────────┤
│                              │
│ Title:                       │
│ ┌────────────────────────┐   │
│ │                    |   │   │  ← focused, cursor ready
│ └────────────────────────┘   │
│                              │
│ Description:                 │
│ ┌────────────────────────┐   │
│ │                        │   │
│ └────────────────────────┘   │
│                              │
│ Status: PENDING              │  ← default, not editable on create
│                              │
│ Priority: [ 3 ▼ ]           │  ← default 3
│                              │
│ Due date:                    │
│ [ Select date...   📅 ]     │  ← optional
│                              │
└──────────────────────────────┘
```

Sub-tasks and comments sections don't appear until after the task is saved.

### Interactions

| Action                     | Behavior                                              |
|----------------------------|-------------------------------------------------------|
| Tap ✏️ (edit)              | Switch to edit mode: fields become editable            |
| Tap Save                   | Validate (title required), save to Room, back to view  |
| Tap Cancel                 | Discard changes, back to view mode                     |
| Change Parent (edit mode)  | Opens picker dialog to select new parent or "None"     |
| Tap sub-task card          | Navigate to TaskDetailScreen for that child            |
| Tap "Add Child"            | Navigate to TaskDetailScreen in new-task mode          |
| Tap breadcrumb segment     | Navigate to TaskDetailScreen for that ancestor         |
| Tap send comment           | Add comment, clear input, scroll to new comment        |
| Long-press comment         | Delete option                                          |
| Back button                | If in edit mode → cancel edit. If in view → pop back.  |

### Breadcrumb Bar

Horizontal scrollable row showing the full hierarchy path:

```
Root > Theme A > Sub-task 1 > Action item 1.1
 ↑       ↑          ↑              ↑
 tap     tap        tap         current (not tappable)
```

- Each segment except the current one is tappable → navigates to that task's detail
- "Root" navigates back to TaskListScreen
- Auto-scrolls to show the current (rightmost) segment

---

## Screen 4: SettingsScreen

### Route: `settings`

Account info, backup controls, security, and sign-out.

### Layout

```
┌──────────────────────────────┐
│ ← Settings                   │
├──────────────────────────────┤
│                              │
│ Account                      │
│ ┌──────────────────────────┐ │
│ │ John Doe                 │ │
│ │ john@gmail.com           │ │
│ └──────────────────────────┘ │
│                              │
│ Backup                       │
│ ┌──────────────────────────┐ │
│ │ Last sync: 2 hours ago   │ │
│ │                          │ │
│ │ [ Sync Now ]             │ │
│ │                          │ │
│ │ Sync status: Idle        │ │  ← or "Syncing..." with spinner
│ └──────────────────────────┘ │
│                              │
│ Security                     │
│ ┌──────────────────────────┐ │
│ │ [ Change Passphrase ]    │ │
│ └──────────────────────────┘ │
│                              │
│ ┌──────────────────────────┐ │
│ │ [ Sign Out ]             │ │
│ └──────────────────────────┘ │
│                              │
│ App version: 1.0             │
│                              │
└──────────────────────────────┘
```

### Change Passphrase Flow

```
┌──────────────────────────────┐
│                              │
│   Change Passphrase          │
│                              │
│   Current passphrase:        │
│   ┌────────────────────────┐ │
│   │ ••••••••               │ │
│   └────────────────────────┘ │
│                              │
│   New passphrase:            │
│   ┌────────────────────────┐ │
│   │ ••••••••               │ │
│   └────────────────────────┘ │
│   Confirm new passphrase:    │
│   ┌────────────────────────┐ │
│   │ ••••••••               │ │
│   └────────────────────────┘ │
│                              │
│   [ Cancel ]  [ Change ]     │
│                              │
└──────────────────────────────┘
```

### Sign Out Behavior

- Clears sign-in state from SharedPreferences
- Does NOT clear local Room DB (data persists locally)
- Navigates to AuthScreen
- On next sign-in, local data is still there. Backup resumes.

---

## Navigation Summary

```kotlin
sealed class Screen(val route: String) {
    object Auth : Screen("auth")
    object TaskList : Screen("tasklist")
    object TaskDetail : Screen("taskdetail/{taskId}") {
        fun createRoute(taskId: String) = "taskdetail/$taskId"
    }
    object NewTask : Screen("taskdetail/new?parentId={parentId}") {
        fun createRoute(parentId: String? = null): String {
            return if (parentId != null) "taskdetail/new?parentId=$parentId"
            else "taskdetail/new"
        }
    }
    object Settings : Screen("settings")
}
```

### Start Destination

- If signed in → `TaskList`
- If not signed in → `Auth`

---

## ViewModels

### TaskListViewModel

```kotlin
data class TaskListUiState(
    val themes: List<Task> = emptyList(),              // root PENDING tasks
    val actionable: List<TaskWithPath> = emptyList(),  // leaf PENDING tasks + hierarchy path
    val searchResults: List<TaskWithPath> = emptyList(),// search results (all statuses)
    val searchQuery: String = "",
    val selectedTab: Tab = Tab.THEMES,
    val isLoading: Boolean = true
)

data class TaskWithPath(
    val task: Task,
    val path: List<String>    // e.g., ["Theme A", "Sub-task 1"]
)

enum class Tab { THEMES, ACTIONABLE, SEARCH }
```

### TaskDetailViewModel

```kotlin
data class TaskDetailUiState(
    val task: Task? = null,
    val children: List<Task> = emptyList(),
    val comments: List<Comment> = emptyList(),
    val breadcrumbs: List<Task> = emptyList(),
    val childCount: Int = 0,
    val isEditing: Boolean = false,
    val isNewTask: Boolean = false,
    val isLoading: Boolean = true
)

// Edit state held separately
data class EditState(
    val title: String = "",
    val description: String = "",
    val status: TaskStatus = TaskStatus.PENDING,
    val priority: Int = 3,              // 1 (highest) to 5 (lowest)
    val dueDate: Long? = null,          // epoch millis, null = no due date
    val parentId: String? = null        // null = root-level theme
)
```

### AuthViewModel

```kotlin
data class AuthUiState(
    val isSignedIn: Boolean = false,
    val isLoading: Boolean = false,
    val hasCloudBackup: Boolean = false,
    val needsPassphraseCreation: Boolean = false,
    val needsPassphraseEntry: Boolean = false,
    val error: String? = null,
    val userName: String? = null,
    val userEmail: String? = null
)
```

### SettingsViewModel

```kotlin
data class SettingsUiState(
    val userName: String = "",
    val userEmail: String = "",
    val lastSyncTime: Long? = null,
    val isSyncing: Boolean = false,
    val syncError: String? = null
)
```
