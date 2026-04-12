import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import styles from './SignIn.module.css';

export default function SignIn() {
  const auth = useAuth();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');

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
      </div>
    </div>
  );
}
