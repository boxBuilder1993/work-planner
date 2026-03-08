declare global {
  interface Window {
    google: {
      accounts: {
        oauth2: {
          initTokenClient(config: {
            client_id: string;
            scope: string;
            callback: (response: { access_token?: string; error?: string }) => void;
          }): { requestAccessToken(): void };
          revoke(token: string, callback?: () => void): void;
        };
      };
    };
  }
}

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string;
const SCOPES = 'https://www.googleapis.com/auth/drive.appdata';

export function requestAccessToken(): Promise<string> {
  return new Promise((resolve, reject) => {
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: CLIENT_ID,
      scope: SCOPES,
      callback: (response) => {
        if (response.error) {
          reject(new Error(response.error));
        } else if (response.access_token) {
          resolve(response.access_token);
        } else {
          reject(new Error('No access token returned'));
        }
      },
    });
    client.requestAccessToken();
  });
}

export function revokeToken(token: string): Promise<void> {
  return new Promise((resolve) => {
    window.google.accounts.oauth2.revoke(token, () => {
      resolve();
    });
  });
}

export async function fetchUserInfo(
  token: string,
): Promise<{ email: string; name: string }> {
  const res = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('Failed to fetch user info');
  const data = await res.json();
  return { email: data.email, name: data.name };
}
