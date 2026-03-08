import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useTasks } from '../hooks/useTasks';
import styles from './SignIn.module.css';

export default function SignIn() {
  const auth = useAuth();
  const { loadFromRestore } = useTasks();

  if (auth.isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.card}>
          <div className="spinner spinner-large" />
        </div>
      </div>
    );
  }

  if (auth.needsPassphraseCreation) {
    return <PassphraseCreation />;
  }

  if (auth.needsPassphraseEntry) {
    return <PassphraseEntry onRestored={loadFromRestore} />;
  }

  return <SignInContent />;
}

function SignInContent() {
  const { signIn, error } = useAuth();

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>WorkPlanner</h1>
        <p className={styles.subtitle}>
          Organize your tasks and themes
        </p>
        {error && <p className={styles.error}>{error}</p>}
        <button className={styles.signInButton} onClick={signIn}>
          Sign in with Google
        </button>
      </div>
    </div>
  );
}

function PassphraseCreation() {
  const { createPassphrase, error, isLoading } = useAuth();
  const [passphrase, setPassphrase] = useState('');
  const [confirm, setConfirm] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createPassphrase(passphrase, confirm);
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>Create Passphrase</h1>
        <p className={styles.subtitle}>
          This passphrase encrypts your data on Google Drive.
        </p>
        <form className={styles.form} onSubmit={handleSubmit}>
          <div>
            <label className={styles.label}>Passphrase</label>
            <input
              className={styles.input}
              type="password"
              placeholder="Minimum 8 characters"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              minLength={8}
              required
            />
          </div>
          <div>
            <label className={styles.label}>Confirm Passphrase</label>
            <input
              className={styles.input}
              type="password"
              placeholder="Re-enter passphrase"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
          </div>
          <div className={styles.warning}>
            If you forget this passphrase, your data cannot be recovered.
          </div>
          {error && <p className={styles.error}>{error}</p>}
          <button
            className={styles.primaryButton}
            type="submit"
            disabled={isLoading}
          >
            {isLoading ? 'Creating...' : 'Create'}
          </button>
        </form>
      </div>
    </div>
  );
}

function PassphraseEntry({
  onRestored,
}: {
  onRestored: (
    tasks: Record<string, import('../types').TaskEntity>,
    comments: Record<string, import('../types').CommentEntity>,
  ) => void;
}) {
  const { enterPassphrase, skipRestore, error, isLoading } = useAuth();
  const [passphrase, setPassphrase] = useState('');

  const handleRestore = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const restored = await enterPassphrase(passphrase);
      onRestored(restored.tasks, restored.comments);
    } catch {
      // Error state is handled by AuthContext
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>Restore Backup</h1>
        <p className={styles.subtitle}>
          An existing backup was found. Enter your passphrase to restore.
        </p>
        <form className={styles.form} onSubmit={handleRestore}>
          <div>
            <label className={styles.label}>Passphrase</label>
            <input
              className={styles.input}
              type="password"
              placeholder="Enter your passphrase"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              required
            />
          </div>
          {error && <p className={styles.error}>{error}</p>}
          <div className={styles.buttonGroup}>
            <button
              className={styles.primaryButton}
              type="submit"
              disabled={isLoading}
            >
              {isLoading ? 'Restoring...' : 'Restore'}
            </button>
            <button
              className={styles.secondaryButton}
              type="button"
              onClick={skipRestore}
              disabled={isLoading}
            >
              Skip
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
