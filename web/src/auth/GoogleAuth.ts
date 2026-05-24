declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(config: {
            client_id: string;
            callback: (response: { credential?: string }) => void;
            auto_select?: boolean;
            ux_mode?: 'popup' | 'redirect';
          }): void;
          renderButton(
            parent: HTMLElement,
            options: {
              theme?: 'outline' | 'filled_blue' | 'filled_black';
              size?: 'large' | 'medium' | 'small';
              text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin';
              width?: number;
            },
          ): void;
          prompt(): void;
        };
      };
    };
  }
}

const API_BASE: string = import.meta.env.VITE_API_URL || 'http://localhost:8080';
export const GOOGLE_CLIENT_ID: string = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

/**
 * Exchange a Google ID token for a backend JWT.
 * Backend's `/auth/google` validates the token against GOOGLE_CLIENT_ID.
 */
export async function exchangeGoogleToken(
  idToken: string,
): Promise<{ token: string; user: { id: string; email: string; name: string } }> {
  const res = await fetch(`${API_BASE}/auth/google`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ idToken }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Google sign-in failed: ${body}`);
  }
  const data = await res.json();
  return { token: data.token, user: data.user };
}
