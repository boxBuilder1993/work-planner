import { db } from '@database/init';
import type { TaskEntity, TaskStatus } from '../types';

export class TaskService {
  static async getTasks(): Promise<TaskEntity[]> {
    try {
      const result = db.getAllSync('SELECT * FROM tasks ORDER BY createdAt DESC');
      return (result as any[]).map(row => this.parseTaskRow(row));
    } catch (error) {
      console.error('Error getting tasks:', error);
      return [];
    }
  }

  static async getTaskById(id: string): Promise<TaskEntity | null> {
    try {
      const result = db.getFirstSync('SELECT * FROM tasks WHERE id = ?', [id]);
      return result ? this.parseTaskRow(result as any) : null;
    } catch (error) {
      console.error('Error getting task:', error);
      return null;
    }
  }

  static async createTask(task: Omit<TaskEntity, 'id' | 'createdAt' | 'updatedAt'>): Promise<TaskEntity> {
    const id = Math.random().toString(36).substring(7);
    const now = Date.now();

    try {
      db.runSync(
        `INSERT INTO tasks (id, parentId, title, description, status, priority, dueDate, taskDate, plannedTime, duration, aiEnabled, props, createdAt, updatedAt)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          id,
          task.parentId,
          task.title,
          task.description,
          task.status,
          task.priority,
          task.dueDate,
          task.taskDate,
          task.plannedTime,
          task.duration,
          task.aiEnabled ? 1 : 0,
          JSON.stringify(task.props),
          now,
          now,
        ]
      );

      return {
        id,
        ...task,
        createdAt: now,
        updatedAt: now,
      };
    } catch (error) {
      console.error('Error creating task:', error);
      throw error;
    }
  }

  static async updateTask(id: string, updates: Partial<TaskEntity>): Promise<TaskEntity | null> {
    const now = Date.now();
    const current = await this.getTaskById(id);

    if (!current) return null;

    const updated = { ...current, ...updates, updatedAt: now };

    try {
      db.runSync(
        `UPDATE tasks SET title = ?, description = ?, status = ?, priority = ?, dueDate = ?, taskDate = ?, plannedTime = ?, duration = ?, aiEnabled = ?, props = ?, updatedAt = ? WHERE id = ?`,
        [
          updated.title,
          updated.description,
          updated.status,
          updated.priority,
          updated.dueDate,
          updated.taskDate,
          updated.plannedTime,
          updated.duration,
          updated.aiEnabled ? 1 : 0,
          JSON.stringify(updated.props),
          now,
          id,
        ]
      );

      return updated;
    } catch (error) {
      console.error('Error updating task:', error);
      throw error;
    }
  }

  static async deleteTask(id: string): Promise<boolean> {
    try {
      db.runSync('DELETE FROM tasks WHERE id = ?', [id]);
      db.runSync('DELETE FROM comments WHERE taskId = ?', [id]);
      db.runSync('DELETE FROM repeatingTasks WHERE taskId = ?', [id]);
      return true;
    } catch (error) {
      console.error('Error deleting task:', error);
      return false;
    }
  }

  private static parseTaskRow(row: any): TaskEntity {
    return {
      id: row.id,
      parentId: row.parentId,
      title: row.title,
      description: row.description,
      status: row.status as TaskStatus,
      priority: row.priority,
      dueDate: row.dueDate,
      taskDate: row.taskDate,
      plannedTime: row.plannedTime,
      duration: row.duration,
      aiEnabled: row.aiEnabled === 1,
      props: row.props ? JSON.parse(row.props) : {},
      createdAt: row.createdAt,
      updatedAt: row.updatedAt,
    };
  }
}
