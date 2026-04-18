import { useState, useEffect } from 'react';
import type { Profile } from '../api/profiles';
import { setActiveProfile, listProfiles } from '../api/profiles';
import styles from './ProfileList.module.css';

export function ProfileList() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    try {
      setError(null);
      const data = await listProfiles();
      setProfiles(data);
    } catch (err) {
      console.error('Failed to load profiles:', err);
      setError(err instanceof Error ? err.message : 'Failed to load profiles');
    }
  };

  const handleSetActive = async (profileId: string) => {
    setLoading(true);
    try {
      setError(null);
      await setActiveProfile(profileId);
      await loadProfiles(); // Refresh list
    } catch (err) {
      console.error('Failed to set active profile:', err);
      setError(err instanceof Error ? err.message : 'Failed to set active profile');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.profileList}>
      {error && <div className={styles.error}>{error}</div>}
      {profiles.length === 0 ? (
        <p className={styles.noProfiles}>No profiles available</p>
      ) : (
        profiles.map((profile) => (
          <div
            key={profile.id}
            className={`${styles.profileItem} ${profile.is_active ? styles.active : ''}`}
          >
            <div className={styles.profileInfo}>
              <h3>{profile.name}</h3>
              {profile.is_active && <span className={styles.activeBadge}>Active</span>}
            </div>
            <button
              onClick={() => handleSetActive(profile.id)}
              disabled={profile.is_active || loading}
              className={styles.setActiveBtn}
            >
              {profile.is_active ? 'Current' : 'Set as Active'}
            </button>
          </div>
        ))
      )}
    </div>
  );
}
