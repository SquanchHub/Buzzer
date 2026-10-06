const BASE = '/api';

/**
 * Pick a readable message out of an error response body. The backend sends
 * {error, message} for app errors, {detail: string} for HTTPException, and
 * {detail: [{loc, msg}, ...]} for request validation errors.
 */
function errorMessage(body: unknown, status: number): string {
  const b = (body ?? {}) as { message?: unknown; detail?: unknown; error?: unknown };
  if (typeof b.message === 'string' && b.message) return b.message;
  if (typeof b.detail === 'string' && b.detail) return b.detail;
  if (Array.isArray(b.detail) && b.detail.length > 0) {
    return b.detail
      .map((item) => {
        const { loc, msg } = (item ?? {}) as { loc?: unknown; msg?: unknown };
        const text = typeof msg === 'string' ? msg : 'Invalid value';
        const field = Array.isArray(loc) ? loc.filter(p => p !== 'body').pop() : undefined;
        return field !== undefined ? `${field}: ${text}` : text;
      })
      .join('; ');
  }
  if (typeof b.error === 'string' && b.error) return b.error;
  return `HTTP ${status}`;
}

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('token');
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers as Record<string, string> ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(errorMessage(err, res.status));
  }
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : ({} as T);
}

/** Trigger a file download from a fetch response */
async function downloadFetch(path: string): Promise<void> {
  const token = localStorage.getItem('token');
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(errorMessage(err, res.status));
  }
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : 'download';
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'PUT',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
  /** POST multipart/form-data (for file uploads) */
  postForm: <T>(path: string, form: FormData) => {
    const token = localStorage.getItem('token');
    return fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(errorMessage(err, res.status));
      }
      const text = await res.text();
      return (text ? JSON.parse(text) : {}) as T;
    });
  },
  download: downloadFetch,
};

// ── Question images (T8, docs/plans/t8-image-support.md D4) ───────────────────
// Bytes are never fetched here: lib/images.ts loads them with the bearer token.

export interface ImageItem {
  id: number;
  course_id: number;
  content_type: string;
  width: number;
  height: number;
  byte_size: number;
  created_at: string | null;
  uploaded_by_name: string | null;
  reference_count: number;
}

export interface ImagePage {
  items: ImageItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReplaceResult {
  id: number; // the image the questions now use
  replaced_id: number;
  repointed_questions: number;
  old_deleted: boolean;
}

/** One page (24) of a course's images, newest first. */
export function listImages(courseId: number, page = 1, unusedOnly = false): Promise<ImagePage> {
  const unused = unusedOnly ? '&unused=true' : '';
  return api.get<ImagePage>(`/images?course_id=${courseId}&page=${page}${unused}`);
}

/** Upload into a course. Identical bytes already in the course return that image. */
export function uploadImage(courseId: number, file: File): Promise<ImageItem> {
  const form = new FormData();
  form.append('file', file);
  form.append('course_id', String(courseId));
  return api.postForm<ImageItem>('/images', form);
}

/** Replace an image everywhere the caller may edit; the old id is deleted once unused. */
export function replaceImage(imageId: number, file: File): Promise<ReplaceResult> {
  const form = new FormData();
  form.append('file', file);
  return api.postForm<ReplaceResult>(`/images/${imageId}/replace`, form);
}

export function deleteImage(imageId: number): Promise<void> {
  return api.delete<void>(`/images/${imageId}`);
}

/** The file types the server accepts (it checks the bytes, not this list). */
export const IMAGE_ACCEPT = 'image/png,image/jpeg,image/webp';
