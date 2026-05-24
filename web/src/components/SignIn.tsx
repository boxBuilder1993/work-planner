import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { GOOGLE_CLIENT_ID } from '../auth/GoogleAuth';
import styles from './SignIn.module.css';

export default function SignIn() {
  const auth = useAuth();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [showEmailFallback, setShowEmailFallback] = useState(false);
  const googleButtonRef = useRef<HTMLDivElement>(null);

  // Render the "Sign in with Google" button as soon as the GIS script is ready.
  // The script tag in index.html is async-loaded; we poll briefly for window.google.
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
          if (response.credential) {
            void auth.signInWithGoogle(response.credential);
          }
        },
        ux_mode: 'popup',
      });
      google.accounts.id.renderButton(googleButtonRef.current, {
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        width: 280,
      });
    };
    tryRender();
    return () => {
      cancelled = true;
    };
  }, [auth]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await auth.signIn(email.trim(), name.trim());
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>WorkPlanner</h1>
        <p className={styles.subtitle}>Organize your tasks and themes</p>
        {auth.error && <p className={styles.error}>{auth.error}</p>}

        {GOOGLE_CLIENT_ID ? (
          <div className={styles.googleSection}>
            <div ref={googleButtonRef} className={styles.googleButton} />
          </div>
        ) : (
          <p className={styles.error}>
            Google sign-in unavailable (VITE_GOOGLE_CLIENT_ID not configured).
          </p>
        )}

        {!showEmailFallback ? (
          <button
            type="button"
            className={styles.linkButton}
            onClick={() => setShowEmailFallback(true)}
          >
            Or sign in with email
          </button>
        ) : (
          <form className={styles.form} onSubmit={handleSubmit}>
            <div>
              <label className={styles.label}>Email</label>
              <input
                className={styles.input}
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div>
              <label className={styles.label}>Name</label>
              <input
                className={styles.input}
                type="text"
                placeholder="Your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <button
              className={styles.primaryButton}
              type="submit"
              disabled={auth.isLoading || !email}
            >
              {auth.isLoading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
