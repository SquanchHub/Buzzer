/**
 * A course's image library (T8, docs/plans/t8-image-support.md D4, D6): view, upload,
 * replace and delete the images questions in this course can use.
 *
 * Copied from frontend/admin/src/pages/ImagesPage.tsx (the apps share no code); only the
 * page header differs (each app's own layout) — keep the library part in sync.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, RefreshCw, Trash2, Upload } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { ImageThumb } from '../components/ImageThumb';
import {
  IMAGE_ACCEPT,
  deleteImage,
  listImages,
  replaceImage,
  uploadImage,
  type ImageItem,
  type ImagePage,
} from '../lib/api';

function kb(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}

function usedBy(n: number): string {
  return n === 0 ? 'Unused' : `Used by ${n} question${n === 1 ? '' : 's'}`;
}

export default function ImagesPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const course = Number(courseId);

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <Link to={`/courses/${course}`} className="text-sm text-ink-muted hover:text-ink">
          ← Course
        </Link>
        <h1 className="font-display text-3xl font-extrabold tracking-tight text-ink">Images</h1>
      </div>
      <ImageLibrary courseId={course} />
    </div>
  );
}

function ImageLibrary({ courseId }: { courseId: number }) {
  const [page, setPage] = useState(1);
  const [unusedOnly, setUnusedOnly] = useState(false);
  const [data, setData] = useState<ImagePage | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const uploadInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    listImages(courseId, page, unusedOnly)
      .then((d) => {
        // Deleting the last image on a page leaves it empty: step back.
        if (d.items.length === 0 && page > 1) setPage(page - 1);
        else setData(d);
      })
      .catch((e: Error) => setError(e.message));
  }, [courseId, page, unusedOnly]);

  useEffect(load, [load]);

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      setNotice(await action());
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function upload(file: File) {
    return run(async () => {
      const image = await uploadImage(courseId, file);
      setPage(1);
      return `Uploaded image #${image.id}.`;
    });
  }

  function replace(image: ImageItem, file: File) {
    return run(async () => {
      const r = await replaceImage(image.id, file);
      const kept = r.old_deleted ? '' : ` Image #${image.id} is kept: games you can't edit still use it.`;
      return `Replaced with image #${r.id}; ${r.repointed_questions} question(s) updated.${kept}`;
    });
  }

  function remove(image: ImageItem) {
    if (!window.confirm(`Delete image #${image.id}? This can't be undone.`)) return;
    return run(async () => {
      await deleteImage(image.id);
      return `Deleted image #${image.id}.`;
    });
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-muted">
          PNG, JPEG or WebP, up to 2 MB and 4096 px per side. Replacing an image updates every
          question you can edit that uses it.
        </p>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-ink-muted">
            <input
              type="checkbox"
              checked={unusedOnly}
              onChange={(e) => {
                setUnusedOnly(e.target.checked);
                setPage(1);
              }}
              className="h-4 w-4 accent-accent"
            />
            Unused only
          </label>
          <input
            ref={uploadInput}
            type="file"
            accept={IMAGE_ACCEPT}
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = '';
              if (file) upload(file);
            }}
          />
          <Button size="sm" disabled={busy} onClick={() => uploadInput.current?.click()}>
            <Upload size={14} className="mr-1" aria-hidden="true" /> Upload
          </Button>
        </div>
      </div>

      {error && <p className="text-sm text-danger-ink" role="alert">{error}</p>}
      {notice && <p className="text-sm text-success-ink" role="status">{notice}</p>}

      {!data ? (
        <p className="text-ink-muted">Loading images…</p>
      ) : data.items.length === 0 ? (
        <Card>
          <CardContent>
            <p className="text-ink-muted">
              {unusedOnly ? 'No unused images.' : 'No images in this course yet.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((image) => (
            <ImageCard
              key={image.id}
              image={image}
              busy={busy}
              onReplace={(file) => replace(image, file)}
              onDelete={() => remove(image)}
            />
          ))}
        </ul>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm text-ink-muted">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            aria-label="Previous page"
          >
            <ChevronLeft size={14} aria-hidden="true" />
          </Button>
          Page {page} of {pages}
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pages}
            onClick={() => setPage((p) => p + 1)}
            aria-label="Next page"
          >
            <ChevronRight size={14} aria-hidden="true" />
          </Button>
        </div>
      )}
    </div>
  );
}

interface ImageCardProps {
  image: ImageItem;
  busy: boolean;
  onReplace: (file: File) => void;
  onDelete: () => void;
}

function ImageCard({ image, busy, onReplace, onDelete }: ImageCardProps) {
  const replaceInput = useRef<HTMLInputElement>(null);
  const used = image.reference_count > 0;
  return (
    <li className="rounded-xl border border-line-soft bg-surface p-3">
      <ImageThumb imageId={image.id} alt={`Image ${image.id}`} className="aspect-[4/3] w-full" />
      <div className="mt-2 space-y-0.5 text-sm">
        <p className="font-medium text-ink">#{image.id}</p>
        <p className="text-ink-muted">
          {image.width}×{image.height} · {kb(image.byte_size)} · {image.content_type.replace('image/', '').toUpperCase()}
        </p>
        <p className="text-ink-muted">Uploaded by {image.uploaded_by_name ?? 'a deleted user'}</p>
        <p className={used ? 'text-ink' : 'text-warning-ink'}>{usedBy(image.reference_count)}</p>
      </div>
      <div className="mt-3 flex gap-2">
        <input
          ref={replaceInput}
          type="file"
          accept={IMAGE_ACCEPT}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (file) onReplace(file);
          }}
        />
        <Button variant="outline" size="sm" disabled={busy} onClick={() => replaceInput.current?.click()}>
          <RefreshCw size={14} className="mr-1" aria-hidden="true" /> Replace
        </Button>
        <Button
          variant="destructive"
          size="sm"
          disabled={busy || used}
          onClick={onDelete}
          title={used ? 'Remove it from every question first' : undefined}
        >
          <Trash2 size={14} className="mr-1" aria-hidden="true" /> Delete
        </Button>
      </div>
      {used && (
        <p className="mt-2 text-xs text-ink-soft">Remove it from every question to delete it.</p>
      )}
    </li>
  );
}
