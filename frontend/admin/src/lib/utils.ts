import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * The `role` claim of a JWT, or null if the token is missing, malformed or expired.
 * Decoded without verifying the signature: this only steers the UI (the server
 * enforces require_admin on every /api/admin request).
 */
export function tokenRole(token: string | null): string | null {
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    if (Date.now() / 1000 >= (payload.exp ?? 0)) return null;
    return typeof payload.role === 'string' ? payload.role : null;
  } catch {
    return null;
  }
}
