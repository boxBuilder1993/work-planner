const API_BASE: string = import.meta.env.VITE_API_URL || 'http://localhost:8080';

type AuthResult = { token: string; user: { id: string; email: string; name: string } };

function post(path: string, body: unknown, token?: string): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
}

async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const j = await res.json();
    return j.error || fallback;
  } catch {
    return fallback;
  }
}

export async function registerWithPassword(email: string, name: string, password: string): Promise<AuthResult> {
  const res = await post('/auth/register', { email, name, password });
  if (!res.ok) throw new Error(await errorMessage(res, 'Registration failed'));
  const data = await res.json();
  return { token: data.token, user: data.user };
}

export async function loginWithPassword(email: string, password: string): Promise<AuthResult> {
  const res = await post('/auth/login', { email, password });
  if (!res.ok) throw new Error(await errorMessage(res, 'Login failed'));
  const data = await res.json();
  return { token: data.token, user: data.user };
}

/** Set/change the current user's password (requires an authenticated token). */
export async function setPassword(password: string, token: string): Promise<void> {
  const res = await post('/auth/password', { password }, token);
  if (!res.ok) throw new Error(await errorMessage(res, 'Failed to set password'));
}
