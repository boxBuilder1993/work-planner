import * as SQLite from 'expo-sqlite';

const DATABASE_NAME = 'workplanner.db';

export const db = SQLite.openDatabaseSync(DATABASE_NAME);

export async function initializeDatabase() {
  try {
    // Initialize tables for offline-first sync
    db.execSync(`
      CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        parentId TEXT,
        title TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL,
        dueDate INTEGER,
        taskDate INTEGER,
        plannedTime INTEGER,
        duration INTEGER,
        aiEnabled INTEGER NOT NULL,
        props TEXT,
        createdAt INTEGER NOT NULL,
        updatedAt INTEGER NOT NULL,
        synced INTEGER DEFAULT 0,
        syncedAt INTEGER
      );

      CREATE TABLE IF NOT EXISTS comments (
        id TEXT PRIMARY KEY,
        taskId TEXT NOT NULL,
        text TEXT NOT NULL,
        parentCommentId TEXT,
        commentType TEXT NOT NULL,
        createdBy TEXT,
        proposalStatus TEXT,
        proposalFeedback TEXT,
        createdAt INTEGER NOT NULL,
        updatedAt INTEGER NOT NULL,
        synced INTEGER DEFAULT 0,
        syncedAt INTEGER,
        FOREIGN KEY (taskId) REFERENCES tasks(id)
      );

      CREATE TABLE IF NOT EXISTS repeatingTasks (
        id TEXT PRIMARY KEY,
        taskId TEXT NOT NULL,
        intervalDays INTEGER NOT NULL,
        startDate INTEGER NOT NULL,
        lastCreatedAt INTEGER,
        createdAt INTEGER NOT NULL,
        updatedAt INTEGER NOT NULL,
        synced INTEGER DEFAULT 0,
        syncedAt INTEGER,
        FOREIGN KEY (taskId) REFERENCES tasks(id)
      );

      CREATE TABLE IF NOT EXISTS syncQueue (
        id TEXT PRIMARY KEY,
        operation TEXT NOT NULL,
        tableName TEXT NOT NULL,
        recordId TEXT NOT NULL,
        payload TEXT,
        createdAt INTEGER NOT NULL,
        retryCount INTEGER DEFAULT 0
      );

      CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
      CREATE INDEX IF NOT EXISTS idx_tasks_dueDate ON tasks(dueDate);
      CREATE INDEX IF NOT EXISTS idx_tasks_parentId ON tasks(parentId);
      CREATE INDEX IF NOT EXISTS idx_comments_taskId ON comments(taskId);
      CREATE INDEX IF NOT EXISTS idx_repeatingTasks_taskId ON repeatingTasks(taskId);
    `);

    console.log('Database initialized successfully');
  } catch (error) {
    console.error('Database initialization error:', error);
    throw error;
  }
}

export function closeDatabase() {
  db.closeSync();
}
