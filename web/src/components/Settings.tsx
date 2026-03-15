import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useTasks } from '../hooks/useTasks';
import styles from './Settings.module.css';

export default function Settings() {
  const navigate = useNavigate();
  const auth = useAuth();
  const taskStore = useTasks();

  const handleSignOut = () => {
    if (!window.confirm('Sign out?')) return;
    taskStore.clearAll();
    auth.signOut();
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

        {/* Sign Out */}
        <button className={styles.signOutButton} onClick={handleSignOut}>
          Sign Out
        </button>
      </div>
    </div>
  );
}
