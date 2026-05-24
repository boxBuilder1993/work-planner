/**
 * Theme mode persistence + application.
 *
 * - `system`: no `data-theme` attribute on <html>; CSS falls through to
 *   the prefers-color-scheme media query.
 * - `light` / `dark`: explicit `data-theme="<value>"` on <html>; the CSS
 *   tokens in index.css apply that scheme regardless of system setting.
 *
 * Persisted in localStorage so the choice survives reloads.
 */

import { useEffect, useState } from 'react';

export type ThemeMode = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'workplanner_theme_mode';

function readStored(): ThemeMode {
  if (typeof window === 'undefined') return 'system';
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return raw === 'light' || raw === 'dark' ? raw : 'system';
}

function applyToDocument(mode: ThemeMode): void {
  const html = document.documentElement;
  if (mode === 'system') {
    html.removeAttribute('data-theme');
  } else {
    html.setAttribute('data-theme', mode);
  }
}

/** Apply the persisted theme at app startup. Call once from main.tsx. */
export function initTheme(): void {
  applyToDocument(readStored());
}

/**
 * Reactive hook for components that need to read or change the theme
 * (e.g. Settings). Returns the current mode and a setter that persists
 * + re-applies in one call.
 */
export function useThemeMode(): {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
} {
  const [mode, setModeState] = useState<ThemeMode>(readStored);

  // Keep <html data-theme> in sync if some other tab changes the setting.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY) return;
      const next = readStored();
      setModeState(next);
      applyToDocument(next);
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setMode = (next: ThemeMode) => {
    window.localStorage.setItem(STORAGE_KEY, next);
    setModeState(next);
    applyToDocument(next);
  };

  return { mode, setMode };
}
