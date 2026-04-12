import { db } from '@database/init';

export interface SyncQueueItem {
  id: string;
  operation: 'CREATE' | 'UPDATE' | 'DELETE';
  tableName: string;
  recordId: string;
  payload?: any;
  createdAt: number;
  retryCount: number;
}

export class SyncService {
  private static MAX_RETRIES = 3;
  private static SYNC_INTERVAL = 30000; // 30 seconds

  static async addToQueue(
    operation: 'CREATE' | 'UPDATE' | 'DELETE',
    tableName: string,
    recordId: string,
    payload?: any
  ): Promise<void> {
    const id = Math.random().toString(36).substring(7);
    
    try {
      db.runSync(
        `INSERT INTO syncQueue (id, operation, tableName, recordId, payload, createdAt, retryCount)
         VALUES (?, ?, ?, ?, ?, ?, ?)`,
        [
          id,
          operation,
          tableName,
          recordId,
          payload ? JSON.stringify(payload) : null,
          Date.now(),
          0,
        ]
      );
    } catch (error) {
      console.error('Error adding to sync queue:', error);
      throw error;
    }
  }

  static async getQueue(): Promise<SyncQueueItem[]> {
    try {
      const result = db.getAllSync(
        'SELECT * FROM syncQueue ORDER BY createdAt ASC LIMIT 100'
      );
      return (result as any[]).map(row => ({
        id: row.id,
        operation: row.operation,
        tableName: row.tableName,
        recordId: row.recordId,
        payload: row.payload ? JSON.parse(row.payload) : undefined,
        createdAt: row.createdAt,
        retryCount: row.retryCount,
      }));
    } catch (error) {
      console.error('Error getting sync queue:', error);
      return [];
    }
  }

  static async processSyncQueue(
    syncHandler: (item: SyncQueueItem) => Promise<boolean>
  ): Promise<void> {
    const queue = await this.getQueue();

    for (const item of queue) {
      if (item.retryCount >= this.MAX_RETRIES) {
        console.warn(`Max retries reached for ${item.id}`);
        this.removeFromQueue(item.id);
        continue;
      }

      try {
        const success = await syncHandler(item);
        if (success) {
          this.removeFromQueue(item.id);
        } else {
          this.incrementRetryCount(item.id);
        }
      } catch (error) {
        console.error(`Error processing sync item ${item.id}:`, error);
        this.incrementRetryCount(item.id);
      }
    }
  }

  private static removeFromQueue(id: string): void {
    try {
      db.runSync('DELETE FROM syncQueue WHERE id = ?', [id]);
    } catch (error) {
      console.error('Error removing from sync queue:', error);
    }
  }

  private static incrementRetryCount(id: string): void {
    try {
      db.runSync('UPDATE syncQueue SET retryCount = retryCount + 1 WHERE id = ?', [id]);
    } catch (error) {
      console.error('Error incrementing retry count:', error);
    }
  }

  static async markAsSynced(tableName: string, recordId: string): Promise<void> {
    try {
      db.runSync(
        `UPDATE ${tableName} SET synced = 1, syncedAt = ? WHERE id = ?`,
        [Date.now(), recordId]
      );
    } catch (error) {
      console.error('Error marking as synced:', error);
    }
  }
}
