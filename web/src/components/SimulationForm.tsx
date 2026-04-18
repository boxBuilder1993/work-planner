import { useState, useEffect } from 'react';
import type { FormEvent } from 'react';
import type { Profile } from '../api/profiles';
import { listProfiles, getActiveProfile } from '../api/profiles';
import styles from './SimulationForm.module.css';

export function SimulationForm() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    try {
      setError(null);
      setLoading(true);

      // Load all profiles
      const allProfiles = await listProfiles();
      setProfiles(allProfiles);

      // Pre-select active profile when component mounts
      const activeProfile = await getActiveProfile();
      setSelectedProfile(activeProfile.id);
    } catch (err) {
      console.error('Failed to load profiles:', err);
      setError(err instanceof Error ? err.message : 'Failed to load profiles');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!selectedProfile) {
      setError('Please select a profile');
      return;
    }
    console.log('Simulating with profile:', selectedProfile);
    // Here you would trigger the actual simulation/execution with the selected profile
  };

  if (loading) {
    return <div className={styles.loading}>Loading profiles...</div>;
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <h2 className={styles.title}>Run Simulation</h2>

      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.formGroup}>
        <label htmlFor="profile-select" className={styles.label}>
          Select Profile
        </label>
        <select
          id="profile-select"
          value={selectedProfile}
          onChange={(e) => setSelectedProfile(e.target.value)}
          className={styles.select}
        >
          <option value="">-- Select a profile --</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} {p.is_active ? '(Active)' : ''}
            </option>
          ))}
        </select>
      </div>

      <button type="submit" className={styles.submitBtn} disabled={loading || !selectedProfile}>
        Run Simulation
      </button>
    </form>
  );
}
