import { useSyncExternalStore } from 'react';

/** T9 light ("Paper") / dark ("Night") theme runtime (docs/plans/t9-theming.md §5.1).
 * Identical copy in host, player and admin. The first paint is handled by the inline
 * script in index.html; this keeps React in sync and handles the toggle. */
export type Theme = 'light' | 'dark';

const KEY = 'buzzer-theme';
const QUERY = '(prefers-color-scheme: dark)';

export function storedTheme(): Theme | null {
  try {
    const t = localStorage.getItem(KEY);
    return t === 'light' || t === 'dark' ? t : null;
  } catch {
    return null; // storage can throw in private mode
  }
}

export function systemTheme(): Theme {
  return window.matchMedia(QUERY).matches ? 'dark' : 'light';
}

export function effectiveTheme(): Theme {
  return storedTheme() ?? systemTheme();
}

export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
}

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((cb) => cb());

/** Store an explicit choice; from then on the OS preference is ignored (D3). */
export function setTheme(t: Theme) {
  try {
    localStorage.setItem(KEY, t);
  } catch {
    // The choice still applies for this page view.
  }
  applyTheme(t);
  notify();
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  const media = window.matchMedia(QUERY);
  const onMedia = () => {
    if (storedTheme() === null) {
      applyTheme(systemTheme());
      notify();
    }
  };
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY || e.key === null) {
      applyTheme(effectiveTheme());
      notify();
    }
  };
  media.addEventListener('change', onMedia);
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(cb);
    media.removeEventListener('change', onMedia);
    window.removeEventListener('storage', onStorage);
  };
}

export function useTheme(): [Theme, (t: Theme) => void] {
  return [useSyncExternalStore(subscribe, effectiveTheme), setTheme];
}

/** A token as a canvas colour: `cssColor('--success', 0.5)`. Canvas code must also depend
 * on `useTheme()` so it repaints when the theme changes (D10). */
export function cssColor(name: string, alpha = 1): string {
  const channels = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return `rgb(${channels || '128 128 128'} / ${alpha})`;
}
