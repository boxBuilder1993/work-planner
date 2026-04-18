import { useState, useEffect } from 'react';
import { getActiveProfile } from '../api/profiles';
import styles from './Header.module.css';

export function Header() {
  const [activeProfileName, setActiveProfileName] = useState<string>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadActiveProfile();
  }, []);

  const loadActiveProfile = async () => {
    try {
      setLoading(true);
      const profile = await getActiveProfile();
      setActiveProfileName(profile.name);
    } catch (error) {
      // No active profile set
      console.warn('No active profile set:', error);
      setActiveProfileName('No Profile');
    } finally {
      setLoading(false);
    }
  };

  return (
    <header className={styles.appHeader}>
      <div className={styles.headerContent}>
        <h1 className={styles.title}>WorkPlanner</h1>
        <div className={styles.profileDisplay}>
          <span className={styles.profileLabel}>Active Profile:</span>
          <span className={styles.profileName}>
            {loading ? 'Loading...' : activeProfileName}
          </span>
        </div>
      </div>
    </header>
  );
}
