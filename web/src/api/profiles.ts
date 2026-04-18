import { apiFetch, apiPost } from './client';

export interface Profile {
  id: string;
  name: string;
  is_active: boolean;
}

export async function getActiveProfile(): Promise<Profile> {
  const response = await apiFetch<{ active_profile_id?: string }>('/me');

  if (!response.active_profile_id) {
    throw new Error('No active profile set');
  }

  // Fetch full profile details
  return apiFetch<Profile>(`/profiles/${response.active_profile_id}`);
}

export async function setActiveProfile(profileId: string): Promise<Profile> {
  return apiPost<Profile>(`/profiles/${profileId}/activate`, {});
}

export async function listProfiles(): Promise<Profile[]> {
  return apiFetch<Profile[]>('/profiles');
}
