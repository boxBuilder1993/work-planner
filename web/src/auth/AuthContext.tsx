import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import { requestAccessToken, revokeToken, fetchUserInfo } from './GoogleAuth';
import { deriveKey, generateSalt } from '../crypto/encryption';
import { downloadSalt, uploadSalt, hasRemoteBackup, performRestore } from '../backup/backupProcessor';
import { UnauthorizedError } from '../drive/driveApi';
import type { TaskEntity, CommentEntity, RepeatingTaskEntity } from '../types';

interface AuthState {
  accessToken: string | null;
  userName: string | null;
  userEmail: string | null;
  encryptionKey: Uint8Array | null;
  salt: Uint8Array | null;
  isSignedIn: boolean;
  isLoading: boolean;
  needsPassphraseCreation: boolean;
  needsPassphraseEntry: boolean;
  error: string | null;
}

interface AuthContextValue extends AuthState {
  signIn: () => Promise<void>;
  createPassphrase: (passphrase: string, confirm: string) => Promise<void>;
  enterPassphrase: (passphrase: string) => Promise<{
    tasks: Record<string, TaskEntity>;
    comments: Record<string, CommentEntity>;
    repeatingTasks: Record<string, RepeatingTaskEntity>;
  }>;
  skipRestore: () => void;
  signOut: () => Promise<void>;
  handleUnauthorized: () => void;
  getToken: () => string;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const SESSION_KEY = 'workplanner_auth';

function toBase64(arr: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < arr.length; i++) binary += String.fromCharCode(arr[i]);
  return btoa(binary);
}

function fromBase64(b64: string): Uint8Array {
  const binary = atob(b64);
  const arr = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i);
  return arr;
}

function saveSession(accessToken: string, userName: string, userEmail: string, encryptionKey: Uint8Array, salt: Uint8Array): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify({
    accessToken,
    userName,
    userEmail,
    encryptionKey: toBase64(encryptionKey),
    salt: toBase64(salt),
  }));
}

function loadSession(): Pick<AuthState, 'accessToken' | 'userName' | 'userEmail' | 'encryptionKey' | 'salt'> | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data.accessToken || !data.userName || !data.userEmail || !data.encryptionKey || !data.salt) return null;
    return {
      accessToken: data.accessToken,
      userName: data.userName,
      userEmail: data.userEmail,
      encryptionKey: fromBase64(data.encryptionKey),
      salt: fromBase64(data.salt),
    };
  } catch {
    return null;
  }
}

function clearSession(): void {
  sessionStorage.removeItem(SESSION_KEY);
}

let _needsInitialRestore = false;

export function needsInitialRestore(): boolean {
  return _needsInitialRestore;
}

export function clearInitialRestore(): void {
  _needsInitialRestore = false;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const session = loadSession();
    if (session) {
      _needsInitialRestore = true;
      return {
        ...session,
        isSignedIn: true,
        isLoading: false,
        needsPassphraseCreation: false,
        needsPassphraseEntry: false,
        error: null,
      };
    }
    return {
      accessToken: null,
      userName: null,
      userEmail: null,
      encryptionKey: null,
      salt: null,
      isSignedIn: false,
      isLoading: false,
      needsPassphraseCreation: false,
      needsPassphraseEntry: false,
      error: null,
    };
  });

  const signIn = useCallback(async () => {
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const token = await requestAccessToken();
      const userInfo = await fetchUserInfo(token);

      // Check if remote backup exists
      const backupExists = await hasRemoteBackup(token);

      if (backupExists) {
        // Remote salt exists → user has a backup → prompt for passphrase entry
        const remoteSalt = await downloadSalt(token);
        setState((s) => ({
          ...s,
          accessToken: token,
          userName: userInfo.name,
          userEmail: userInfo.email,
          salt: remoteSalt,
          isSignedIn: true,
          isLoading: false,
          needsPassphraseEntry: true,
          needsPassphraseCreation: false,
        }));
      } else {
        // No backup → prompt for passphrase creation
        setState((s) => ({
          ...s,
          accessToken: token,
          userName: userInfo.name,
          userEmail: userInfo.email,
          isSignedIn: true,
          isLoading: false,
          needsPassphraseCreation: true,
          needsPassphraseEntry: false,
        }));
      }
    } catch (err) {
      setState((s) => ({
        ...s,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Sign-in failed',
      }));
    }
  }, []);

  const createPassphrase = useCallback(
    async (passphrase: string, confirm: string) => {
      if (passphrase !== confirm) {
        setState((s) => ({ ...s, error: 'Passphrases do not match' }));
        return;
      }
      if (passphrase.length < 8) {
        setState((s) => ({
          ...s,
          error: 'Passphrase must be at least 8 characters',
        }));
        return;
      }

      setState((s) => ({ ...s, isLoading: true, error: null }));
      try {
        const salt = generateSalt();
        const key = await deriveKey(passphrase, salt);

        // Upload salt to Drive
        await uploadSalt(state.accessToken!, salt);

        saveSession(state.accessToken!, state.userName!, state.userEmail!, key, salt);

        setState((s) => ({
          ...s,
          encryptionKey: key,
          salt,
          isLoading: false,
          needsPassphraseCreation: false,
          needsPassphraseEntry: false,
        }));
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          handleUnauthorized();
          return;
        }
        setState((s) => ({
          ...s,
          isLoading: false,
          error: err instanceof Error ? err.message : 'Failed to create passphrase',
        }));
      }
    },
    [state.accessToken, state.userName, state.userEmail],
  );

  const enterPassphrase = useCallback(
    async (passphrase: string): Promise<{
      tasks: Record<string, TaskEntity>;
      comments: Record<string, CommentEntity>;
      repeatingTasks: Record<string, RepeatingTaskEntity>;
    }> => {
      if (!state.salt) throw new Error('No salt file found on Drive. Please sync from your Android device first, then try again.');

      setState((s) => ({ ...s, isLoading: true, error: null }));
      try {
        const key = await deriveKey(passphrase, state.salt);

        // Attempt restore to verify passphrase is correct
        const restored = await performRestore(state.accessToken!, key);

        saveSession(state.accessToken!, state.userName!, state.userEmail!, key, state.salt!);

        setState((s) => ({
          ...s,
          encryptionKey: key,
          isLoading: false,
          needsPassphraseEntry: false,
          needsPassphraseCreation: false,
        }));

        return restored;
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          handleUnauthorized();
          return { tasks: {}, comments: {}, repeatingTasks: {} };
        }
        setState((s) => ({
          ...s,
          isLoading: false,
          error: 'Incorrect passphrase or corrupted backup',
        }));
        throw err;
      }
    },
    [state.accessToken, state.userName, state.userEmail, state.salt],
  );

  const skipRestore = useCallback(() => {
    // User skips restore — create new salt and key-less state
    // They'll need to create a new passphrase
    setState((s) => ({
      ...s,
      needsPassphraseEntry: false,
      needsPassphraseCreation: true,
      salt: null,
      error: null,
    }));
  }, []);

  const signOut = useCallback(async () => {
    clearSession();
    if (state.accessToken) {
      try {
        await revokeToken(state.accessToken);
      } catch {
        // Ignore revoke errors
      }
    }
    setState({
      accessToken: null,
      userName: null,
      userEmail: null,
      encryptionKey: null,
      salt: null,
      isSignedIn: false,
      isLoading: false,
      needsPassphraseCreation: false,
      needsPassphraseEntry: false,
      error: null,
    });
  }, [state.accessToken]);

  const handleUnauthorized = useCallback(() => {
    clearSession();
    setState((s) => ({
      ...s,
      accessToken: null,
      encryptionKey: null,
      salt: null,
      isSignedIn: false,
      isLoading: false,
      needsPassphraseCreation: false,
      needsPassphraseEntry: false,
      error: 'Session expired. Please sign in again.',
    }));
  }, []);

  const getToken = useCallback((): string => {
    if (!state.accessToken) throw new Error('Not authenticated');
    return state.accessToken;
  }, [state.accessToken]);

  return (
    <AuthContext.Provider
      value={{
        ...state,
        signIn,
        createPassphrase,
        enterPassphrase,
        skipRestore,
        signOut,
        handleUnauthorized,
        getToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
