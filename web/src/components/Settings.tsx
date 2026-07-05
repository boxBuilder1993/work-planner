import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useTasks } from '../hooks/useTasks';
import { useThemeMode, type ThemeMode } from '../theme/themeMode';
import styles from './Settings.module.css';

const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

export default function Settings() {
  const navigate = useNavigate();
  const auth = useAuth();
  const taskStore = useTasks();
  const { mode: themeMode, setMode: setThemeMode } = useThemeMode();

  const handleSignOut = () => {
    if (!window.confirm('Sign out?')) return;
    taskStore.clearAll();
    auth.signOut();
    navigate('/auth', { replace: true });
  };

  return (
    <div className={styles.page}>
      <header className="flex items-center gap-3 border-b px-7 py-4">
        <h1 className="text-[19px] font-semibold tracking-tight">Settings</h1>
      </header>

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

        {/* Appearance card */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Appearance</h2>
          <div className={styles.themePickerLabel}>Theme</div>
          <div className={styles.themePicker} role="radiogroup" aria-label="Theme">
            {THEME_OPTIONS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={themeMode === value}
                className={`${styles.themeOption} ${themeMode === value ? styles.themeOptionActive : ''}`}
                onClick={() => setThemeMode(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Sign Out */}
        <button
          onClick={handleSignOut}
          className="inline-flex h-10 items-center justify-center rounded-lg border px-4 text-[14px] font-medium text-muted-foreground transition-colors hover:border-destructive hover:text-destructive"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
