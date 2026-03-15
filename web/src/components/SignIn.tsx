import { useAuth } from '../auth/AuthContext';
import styles from './SignIn.module.css';

export default function SignIn() {
  const auth = useAuth();

  if (auth.isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.card}>
          <div className="spinner spinner-large" />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>WorkPlanner</h1>
        <p className={styles.subtitle}>
          Organize your tasks and themes
        </p>
        {auth.error && <p className={styles.error}>{auth.error}</p>}
        <button className={styles.signInButton} onClick={auth.signIn}>
          Sign in with Google
        </button>
      </div>
    </div>
  );
}
