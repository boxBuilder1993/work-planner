# WorkPlanner Mobile App

React Native/Expo-based mobile application for the WorkPlanner offline-first task management system.

## Overview

- **Framework**: Expo + React Native
- **Language**: TypeScript
- **Database**: SQLite (via expo-sqlite)
- **Authentication**: Google Sign-In
- **Architecture**: Offline-first with sync queue

## Project Structure

```
src/
├── App.tsx              # Main app component
├── components/          # Reusable React Native components
├── screens/             # Screen components (TaskList, TaskDetail, etc.)
├── services/            # Business logic services
│   ├── taskService.ts   # Task CRUD operations
│   └── syncService.ts   # Offline-first sync handling
├── database/            # SQLite database initialization
│   └── init.ts          # Schema and initialization
└── types/               # TypeScript type definitions (shared with web UI)
    └── index.ts         # Shared types
```

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn
- Expo CLI: `npm install -g eas-cli`
- iOS: Xcode (macOS) or iPhone Simulator
- Android: Android Studio or Android Emulator

### Installation

```bash
# Install dependencies
npm install

# Set up environment
cp .env.example .env
# Edit .env with your configuration
```

### Development

```bash
# Start development server
npm start

# Or run directly on specific platform
npm run ios      # iOS simulator
npm run android  # Android emulator
npm run web      # Web browser
```

### Building

```bash
# Build for iOS
npm run build:ios

# Build for Android
npm run build:android
```

## Architecture

### Offline-First Approach

The app uses SQLite for local storage with a sync queue for offline-first operation:

1. **Local Storage**: All data is stored in SQLite
2. **Sync Queue**: Changes are queued for syncing when online
3. **Background Sync**: Automatic sync when connectivity is restored
4. **Conflict Resolution**: Server-side last-write-wins strategy

### Database Schema

- **tasks**: Main task entities with sync status
- **comments**: Task comments with proposal tracking
- **repeatingTasks**: Recurring task definitions
- **syncQueue**: Pending changes to sync

## Shared Types

The mobile app shares type definitions with the web UI (`ui/src/types/finance.ts`):
- `TaskEntity`
- `CommentEntity`
- `RepeatingTaskEntity`
- Type definitions and constants

## Services

### TaskService

Handle CRUD operations for tasks:
```typescript
await TaskService.getTasks()
await TaskService.getTaskById(id)
await TaskService.createTask(taskData)
await TaskService.updateTask(id, updates)
await TaskService.deleteTask(id)
```

### SyncService

Manage offline-first sync:
```typescript
await SyncService.addToQueue(operation, tableName, recordId, payload)
await SyncService.processSyncQueue(syncHandler)
await SyncService.markAsSynced(tableName, recordId)
```

## Development

### TypeScript Compilation

```bash
npm run typescript
```

### Running Tests

```bash
npm test
```

## Configuration Files

- `app.json`: Expo configuration with iOS/Android settings
- `eas.json`: Expo Application Services (EAS) build config
- `tsconfig.json`: TypeScript compiler options with path aliases
- `.env.example`: Environment variable template

## Next Phases

1. **Schema & Migrations**: Finalize database schema and migration tools
2. **Services**: Implement sync, auth, and API services
3. **UI Components**: Build screens and navigation
4. **Testing**: Add unit and integration tests
5. **Authentication**: Integrate Google Sign-In
6. **Backend Integration**: Connect to WorkPlanner backend API

## License

MIT
