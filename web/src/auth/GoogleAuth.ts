declare global {
  interface Window {
    google: {
      accounts: {
        id: {
          initialize(config: {
            client_id: string;
            callback: (response: { credential?: string; error?: string }) => void;
            auto_select?: boolean;
          }): void;
          prompt(callback?: (notification: { isNotDisplayed: () => boolean; isSkippedMoment: () => boolean }) => void): void;
          renderButton(parent: HTMLElement, options: { theme?: string; size?: string; text?: string }): void;
          revoke(hint: string, callback?: () => void): void;
        };
      };
    };
  }
}

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string;
const API_BASE = import.meta.env.VITE_API_URL as string || 'http://localhost:8080';

/**
 * Initialize Google Identity Services and get an ID token via One Tap or button.
 * Returns a JWT from our backend (not the Google token).
 */
export function requestGoogleSignIn(): Promise<{ token: string; user: { id: string; email: string; name: string } }> {
  return new Promise((resolve, reject) => {
    window.google.accounts.id.initialize({
      client_id: CLIENT_ID,
      callback: async (response) => {
        if (!response.credential) {
          reject(new Error('No credential returned from Google'));
          return;
        }
        try {
          // Exchange Google ID token for our backend JWT
          const res = await fetch(`${API_BASE}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ idToken: response.credential }),
          });
          if (!res.ok) {
            const body = await res.text();
            reject(new Error(`Auth failed: ${body}`));
            return;
          }
          const data = await res.json();
          resolve({ token: data.token, user: data.user });
        } catch (err) {
          reject(err);
        }
      },
    });
    window.google.accounts.id.prompt();
  });
}

export function renderGoogleButton(element: HTMLElement): void {
  window.google.accounts.id.initialize({
    client_id: CLIENT_ID,
    callback: () => {}, // handled by requestGoogleSignIn
  });
  window.google.accounts.id.renderButton(element, {
    theme: 'outline',
    size: 'large',
    text: 'signin_with',
  });
}
