import * as AuthSession from 'expo-auth-session';
import * as SecureStore from 'expo-secure-store';

const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID || '';

interface AuthToken {
  accessToken: string;
  refreshToken?: string;
  expiresIn: number;
}

export const initiateGoogleSignIn = async (): Promise<AuthToken | null> => {
  try {
    const discovery = await AuthSession.fetchDiscoveryAsync(
      'https://accounts.google.com'
    );

    const authResult = await AuthSession.startAsync({
      promptUser: true,
      discovery,
      clientId: GOOGLE_CLIENT_ID,
      redirectUrl: AuthSession.getRedirectUrl(),
      scopes: ['openid', 'profile', 'email'],
    });

    if (authResult.type === 'success') {
      const { access_token, expires_in } = authResult.params;

      // Store token securely
      await SecureStore.setItemAsync('authToken', access_token);

      return {
        accessToken: access_token,
        expiresIn: expires_in,
      };
    }

    return null;
  } catch (error) {
    console.error('Google sign-in failed:', error);
    throw error;
  }
};

export const getStoredAuthToken = async (): Promise<string | null> => {
  try {
    return await SecureStore.getItemAsync('authToken');
  } catch (error) {
    console.error('Failed to get stored auth token:', error);
    return null;
  }
};

export const signOut = async (): Promise<void> => {
  try {
    await SecureStore.deleteItemAsync('authToken');
  } catch (error) {
    console.error('Sign out failed:', error);
  }
};
