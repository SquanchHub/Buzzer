/**
 * Choose an image for a question (T8, docs/plans/t8-image-support.md §3 contract).
 *
 * Shows the chosen image (or nothing) with Choose / Change / Remove buttons. Choosing opens a
 * dialog listing the course's images, 24 per page, with an Upload button; an upload is
 * selected straight away. Only the image id is returned — hotspot measures the aspect ratio
 * from the loaded image itself.
 *
 * Copied into frontend/host/src/components/ImagePicker.tsx (the apps share no code) — keep
 * the two in sync.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, ImagePlus, Upload, X } from 'lucide-react';
import { Button } from './ui/button';
import { ImageThumb } from './ImageThumb';
import { IMAGE_ACCEPT, listImages, uploadImage, type ImagePage } from '../lib/api';

interface ImagePickerProps {
  courseId: number;
  value: number | null;
  onChange: (imageId: number | null) => void;
  /** What the image is for, e.g. "prompt image" or "image for option B" (labels, alt text). */
  label?: string;
}

export function ImagePicker({ courseId, value, onChange, label = 'image' }: ImagePickerProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex items-center gap-3">
      {value !== null && (
        <ImageThumb imageId={value} alt={`Chosen ${label}`} className="h-16 w-24 shrink-0" />
      )}
      <Button type="button" variant="outline" size="sm" onClick={() => setOpen(true)}>
        <ImagePlus size={14} className="mr-1" aria-hidden="true" />
        {value === null ? `Choose ${label}` : 'Change'}
      </Button>
      {value !== null && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onChange(null)}
          aria-label={`Remove ${label}`}
        >
          Remove
        </Button>
      )}
      {open && (
        <PickerDialog
          courseId={courseId}
          current={value}
          label={label}
          onClose={() => setOpen(false)}
          onPick={(id) => {
            onChange(id);
            setOpen(false);
          }}
        />
      )}
    </div>
  );
}

interface PickerDialogProps {
  courseId: number;
  current: number | null;
  label: string;
  onClose: () => void;
  onPick: (imageId: number) => void;
}

function PickerDialog({ courseId, current, label, onClose, onPick }: PickerDialogProps) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ImagePage | null>(null);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    setError('');
    listImages(courseId, page)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [courseId, page]);

  useEffect(load, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function upload(file: File) {
    setUploading(true);
    setError('');
    try {
      const image = await uploadImage(courseId, file);
      onPick(image.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Choose ${label}`}
        className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-xl border border-slate-700 bg-slate-800 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-slate-100">Choose {label}</h2>
          <div className="flex items-center gap-2">
            <input
              ref={fileInput}
              type="file"
              accept={IMAGE_ACCEPT}
              className="hidden"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            />
            <Button
              type="button"
              size="sm"
              disabled={uploading}
              onClick={() => fileInput.current?.click()}
            >
              <Upload size={14} className="mr-1" aria-hidden="true" />
              {uploading ? 'Uploading…' : 'Upload new'}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={onClose} aria-label="Close">
              <X size={16} aria-hidden="true" />
            </Button>
          </div>
        </div>
        <p className="mb-3 text-xs text-slate-400">
          PNG, JPEG or WebP, up to 2 MB and 4096 px per side. Images belong to this course.
        </p>
        {error && <p className="mb-3 text-sm text-red-400">{error}</p>}

        <div className="min-h-0 flex-1 overflow-y-auto">
          {!data ? (
            <p className="text-sm text-slate-400">Loading…</p>
          ) : data.items.length === 0 ? (
            <p className="text-sm text-slate-400">No images in this course yet — upload one.</p>
          ) : (
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {data.items.map((image) => (
                <li key={image.id}>
                  <button
                    type="button"
                    onClick={() => onPick(image.id)}
                    className={
                      'w-full rounded-lg border p-1.5 text-left transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 ' +
                      (image.id === current
                        ? 'border-indigo-500 bg-indigo-500/10'
                        : 'border-slate-700 hover:border-slate-500')
                    }
                  >
                    <ImageThumb
                      imageId={image.id}
                      alt={`Image ${image.id}`}
                      className="aspect-[4/3] w-full"
                    />
                    <span className="mt-1 block text-xs text-slate-400">
                      #{image.id} · {image.width}×{image.height}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {pages > 1 && (
          <div className="mt-4 flex items-center justify-end gap-2 text-sm text-slate-300">
            <Button
              type="button"
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
              type="button"
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
    </div>
  );
}
