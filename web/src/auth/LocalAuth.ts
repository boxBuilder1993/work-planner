const API_BASE: string = import.meta.env.VITE_API_URL || 'http://localhost:8080';

export async function requestLocalSignIn(
  email: string,
  name: string,
): Promise<{ token: string; user: { id: string; email: string; name: string } }> {
  const res = await fetch(`${API_BASE}/auth/local`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, name }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Sign-in failed: ${body}`);
  }
  const data = await res.json();
  return { token: data.token, user: data.user };
}
