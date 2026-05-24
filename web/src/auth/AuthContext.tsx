import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import { requestLocalSignIn } from './LocalAuth';

interface AuthState {
  token: string | null;
  userName: string | null;
  userEmail: string | null;
  isSignedIn: boolean;
  isLoading: boolean;
  error: string | null;
}

interface AuthContextValue extends AuthState {
  signIn: (email: string, name: string) => Promise<void>;
  signOut: () => void;
  getToken: () => string;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const JWT_KEY = 'workplanner_jwt';
const USER_KEY = 'workplanner_user';

function loadSession(): Pick<AuthState, 'token' | 'userName' | 'userEmail'> | null {
  const token = localStorage.getItem(JWT_KEY);
  if (!token) return null;
  try {
    const user = JSON.parse(localStorage.getItem(USER_KEY) || '{}');
    return { token, userName: user.name || null, userEmail: user.email || null };
  } catch {
    return { token, userName: null, userEmail: null };
  }
}

function saveSession(token: string, user: { name: string; email: string }): void {
  localStorage.setItem(JWT_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearSession(): void {
  localStorage.removeItem(JWT_KEY);
  localStorage.removeItem(USER_KEY);
}

// eslint-disable-next-line react-refresh/only-export-components -- quarantined; tracked in task d4dfaff6
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const session = loadSession();
    if (session?.token) {
      return {
        ...session,
        isSignedIn: true,
        isLoading: false,
        error: null,
      };
    }
    return {
      token: null,
      userName: null,
      userEmail: null,
      isSignedIn: false,
      isLoading: false,
      error: null,
    };
  });

  const signIn = useCallback(async (email: string, name: string) => {
    setState((s) => ({ ...s, isLoading: true, error: null }));
    try {
      const { token, user } = await requestLocalSignIn(email, name);
      saveSession(token, { name: user.name, email: user.email });
      setState({
        token,
        userName: user.name,
        userEmail: user.email,
        isSignedIn: true,
        isLoading: false,
        error: null,
      });
    } catch (err) {
      setState((s) => ({
        ...s,
        isLoading: false,
        error: err instanceof Error ? err.message : 'Sign-in failed',
      }));
    }
  }, []);

  const signOut = useCallback(() => {
    clearSession();
    setState({
      token: null,
      userName: null,
      userEmail: null,
      isSignedIn: false,
      isLoading: false,
      error: null,
    });
  }, []);

  const getToken = useCallback((): string => {
    if (!state.token) throw new Error('Not authenticated');
    return state.token;
  }, [state.token]);

  return (
    <AuthContext.Provider value={{ ...state, signIn, signOut, getToken }}>
      {children}
    </AuthContext.Provider>
  );
}
