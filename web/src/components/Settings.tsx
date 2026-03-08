import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useTasks } from '../hooks/useTasks';
import { performBackup, performRestore } from '../backup/backupProcessor';
import { UnauthorizedError } from '../drive/driveApi';
import styles from './Settings.module.css';

export default function Settings() {
  const navigate = useNavigate();
  const auth = useAuth();
  const taskStore = useTasks();

  const [syncing, setSyncing] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [status, setStatus] = useState<{
    message: string;
    type: 'success' | 'error';
  } | null>(null);

  const handleSync = async () => {
    setSyncing(true);
    setStatus(null);
    try {
      const tasksRecord = taskStore.getTasksRecord();
      const commentsRecord = taskStore.getCommentsRecord();
      const repeatingTasksRecord = taskStore.getRepeatingTasksRecord();
      await performBackup(
        auth.getToken(),
        auth.encryptionKey!,
        tasksRecord,
        commentsRecord,
        repeatingTasksRecord,
        auth.salt!,
      );
      setStatus({ message: 'Backup completed successfully', type: 'success' });
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        auth.handleUnauthorized();
        return;
      }
      setStatus({
        message: err instanceof Error ? err.message : 'Backup failed',
        type: 'error',
      });
    } finally {
      setSyncing(false);
    }
  };

  const handleRestore = async () => {
    setRestoring(true);
    setStatus(null);
    try {
      const restored = await performRestore(
        auth.getToken(),
        auth.encryptionKey!,
      );
      taskStore.loadFromRestore(restored.tasks, restored.comments, restored.repeatingTasks);
      const taskCount = Object.keys(restored.tasks).length;
      const commentCount = Object.keys(restored.comments).length;
      const repeatingCount = Object.keys(restored.repeatingTasks).length;
      setStatus({
        message: `Restored ${taskCount} task${taskCount !== 1 ? 's' : ''}, ${commentCount} comment${commentCount !== 1 ? 's' : ''}, and ${repeatingCount} repeating rule${repeatingCount !== 1 ? 's' : ''}`,
        type: 'success',
      });
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        auth.handleUnauthorized();
        return;
      }
      setStatus({
        message: err instanceof Error ? err.message : 'Restore failed',
        type: 'error',
      });
    } finally {
      setRestoring(false);
    }
  };

  const handleSignOut = async () => {
    if (!window.confirm('Sign out? Any unsaved changes will be lost.')) return;
    taskStore.clearAll();
    await auth.signOut();
    navigate('/auth', { replace: true });
  };

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <button className={styles.backButton} onClick={() => navigate(-1)}>
          &larr;
        </button>
        <span className={styles.topBarTitle}>Settings</span>
      </div>

      <div className={styles.content}>
        {/* Account card */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Account</h2>
          <div className={styles.accountInfo}>
            <span className={styles.accountName}>
              {auth.userName ?? 'Unknown'}
            </span>
            <span className={styles.accountEmail}>
              {auth.userEmail ?? ''}
            </span>
          </div>
        </div>

        {/* Backup card */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Google Drive Backup</h2>
          <div className={styles.backupButtons}>
            <button
              className={styles.backupButton}
              onClick={handleSync}
              disabled={syncing || restoring}
            >
              {syncing && <span className="spinner" />}
              {syncing ? 'Syncing...' : 'Sync Now'}
            </button>
            <button
              className={styles.backupButton}
              onClick={handleRestore}
              disabled={syncing || restoring}
            >
              {restoring && <span className="spinner" />}
              {restoring ? 'Restoring...' : 'Restore from Backup'}
            </button>
          </div>
          {status && (
            <div
              className={`${styles.statusMessage} ${
                status.type === 'success'
                  ? styles.statusSuccess
                  : styles.statusError
              }`}
            >
              {status.message}
            </div>
          )}
        </div>

        {/* Sign Out */}
        <button className={styles.signOutButton} onClick={handleSignOut}>
          Sign Out
        </button>
      </div>
    </div>
  );
}
