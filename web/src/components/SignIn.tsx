import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { GOOGLE_CLIENT_ID } from '../auth/GoogleAuth';
import styles from './SignIn.module.css';

export default function SignIn() {
  const auth = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const googleButtonRef = useRef<HTMLDivElement>(null);

  // Render the "Sign in with Google" button as soon as the GIS script is ready.
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || !googleButtonRef.current) return;
    let cancelled = false;
    const tryRender = () => {
      if (cancelled) return;
      const google = window.google;
      if (!google || !googleButtonRef.current) {
        window.setTimeout(tryRender, 100);
        return;
      }
      google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response) => {
          if (response.credential) void auth.signInWithGoogle(response.credential);
        },
        ux_mode: 'popup',
      });
      google.accounts.id.renderButton(googleButtonRef.current, {
        theme: 'outline', size: 'large', text: 'continue_with', width: 280,
      });
    };
    tryRender();
    return () => { cancelled = true; };
  }, [auth]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === 'login') await auth.loginWithPassword(email.trim(), password);
    else await auth.registerWithPassword(email.trim(), name.trim(), password);
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>WorkPlanner</h1>
        <p className={styles.subtitle}>Plan your projects, ship on time</p>
        {auth.error && <p className={styles.error}>{auth.error}</p>}

        {GOOGLE_CLIENT_ID && (
          <>
            <div className={styles.googleSection}>
              <div ref={googleButtonRef} className={styles.googleButton} />
            </div>
            <div className="my-4 flex items-center gap-3 text-[12px] text-muted-foreground">
              <div className="h-px flex-1 bg-border" /> or <div className="h-px flex-1 bg-border" />
            </div>
          </>
        )}

        <form className={styles.form} onSubmit={handleSubmit}>
          {mode === 'register' && (
            <div>
              <label className={styles.label}>Name</label>
              <input className={styles.input} type="text" placeholder="Your name"
                value={name} onChange={(e) => setName(e.target.value)} />
            </div>
          )}
          <div>
            <label className={styles.label}>Email</label>
            <input className={styles.input} type="email" placeholder="you@example.com"
              value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          </div>
          <div>
            <label className={styles.label}>Password</label>
            <input className={styles.input} type="password"
              placeholder={mode === 'register' ? 'At least 8 characters' : 'Your password'}
              value={password} onChange={(e) => setPassword(e.target.value)} required
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={8} />
          </div>
          <button className={styles.primaryButton} type="submit"
            disabled={auth.isLoading || !email || password.length < 8}>
            {auth.isLoading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <button type="button" onClick={() => setMode((m) => (m === 'login' ? 'register' : 'login'))}
          className="mt-3 text-[13px] text-muted-foreground hover:text-foreground">
          {mode === 'login' ? 'No account? Create one' : 'Have an account? Sign in'}
        </button>
      </div>
    </div>
  );
}
