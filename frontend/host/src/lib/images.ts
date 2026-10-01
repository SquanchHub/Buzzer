/**
 * Load a T8 image as an object URL (docs/plans/t7-hotspot.md §4 C3, §7.6).
 *
 * An <img src="/api/images/…"> can't send the bearer token, so the image is
 * fetched with it and handed back as a same-origin blob URL, which a canvas can
 * draw without being tainted. The caller owns the URL: revoke it with
 * URL.revokeObjectURL when done. The default fetch cache mode is kept on
 * purpose, so the server's immutable Cache-Control makes repeat loads local.
 *
 * Copied from player/src/lib/images.ts (the apps share no code) — keep in sync.
 */

export class ImageUnavailableError extends Error {
  constructor(imageId: number, reason: string) {
    super(`Image ${imageId} unavailable: ${reason}`);
    this.name = 'ImageUnavailableError';
  }
}

export async function loadImageUrl(imageId: number): Promise<string> {
  const token = localStorage.getItem('token');
  let res: Response;
  try {
    res = await fetch(`/api/images/${imageId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch {
    throw new ImageUnavailableError(imageId, 'network error');
  }
  if (!res.ok) throw new ImageUnavailableError(imageId, `HTTP ${res.status}`);
  const blob = await res.blob();
  // Guards against a 200 that isn't an image (e.g. an HTML fallback page).
  if (!blob.type.startsWith('image/')) {
    throw new ImageUnavailableError(imageId, `not an image (${blob.type || 'no type'})`);
  }
  return URL.createObjectURL(blob);
}
