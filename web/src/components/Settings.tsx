import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { setPassword } from '../auth/PasswordAuth';
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
  const [pw, setPw] = useState('');
  const [pwBusy, setPwBusy] = useState(false);
  const [pwMsg, setPwMsg] = useState<{ text: string; err: boolean } | null>(null);

  const handleSetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pw.length < 8 || pwBusy) return;
    setPwBusy(true);
    setPwMsg(null);
    try {
      await setPassword(pw, auth.getToken());
      setPw('');
      setPwMsg({ text: 'Password set — you can now sign in with your email + password.', err: false });
    } catch (err) {
      setPwMsg({ text: err instanceof Error ? err.message : 'Failed to set password', err: true });
    } finally {
      setPwBusy(false);
    }
  };

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

        {/* Password card */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Password</h2>
          <p className="mb-3 text-[13px] text-muted-foreground">
            Set a password to sign in with your email — works alongside Google.
          </p>
          <form onSubmit={handleSetPassword} className="flex flex-wrap items-center gap-2">
            <input
              type="password"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              placeholder="New password (min 8 characters)"
              minLength={8}
              autoComplete="new-password"
              className="h-9 min-w-[220px] flex-1 rounded-md border bg-background px-2.5 text-[13px] outline-none focus:border-foreground"
            />
            <button
              type="submit"
              disabled={pwBusy || pw.length < 8}
              className="inline-flex h-9 items-center rounded-md bg-primary px-3 text-[13px] font-medium text-primary-foreground disabled:opacity-50"
            >
              {pwBusy ? 'Saving…' : 'Set password'}
            </button>
          </form>
          {pwMsg && <p className={`mt-2 text-[13px] ${pwMsg.err ? 'text-destructive' : 'text-green-600'}`}>{pwMsg.text}</p>}
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
