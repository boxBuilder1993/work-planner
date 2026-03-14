import { useEffect, useRef } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useTasks } from './useTasks';
import { performBackup } from '../backup/backupProcessor';
import { UnauthorizedError } from '../drive/driveApi';

const SYNC_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Automatically backs up local state to Google Drive every 5 minutes.
 * Must be rendered inside both AuthProvider and TasksProvider.
 */
export function useAutoSync() {
  const auth = useAuth();
  const taskStore = useTasks();
  const syncingRef = useRef(false);

  useEffect(() => {
    if (!auth.isSignedIn || !auth.encryptionKey || !auth.salt) return;

    const sync = async () => {
      if (syncingRef.current) return;
      syncingRef.current = true;
      try {
        const token = auth.getToken();
        await performBackup(
          token,
          auth.encryptionKey!,
          taskStore.getTasksRecord(),
          taskStore.getCommentsRecord(),
          taskStore.getRepeatingTasksRecord(),
          auth.salt!,
        );
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          auth.handleUnauthorized();
        }
        // Silently ignore other errors — next cycle will retry
      } finally {
        syncingRef.current = false;
      }
    };

    const id = setInterval(sync, SYNC_INTERVAL_MS);
    return () => clearInterval(id);
  }, [auth, taskStore]);
}
