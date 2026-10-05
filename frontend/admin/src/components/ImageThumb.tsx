/**
 * Shows a stored image (T8) inside a box, letterboxed (object-contain).
 *
 * An <img src="/api/images/…"> can't send the bearer token, so the image is loaded
 * through lib/images.ts into a blob URL, which is revoked on unmount or id change.
 *
 * Copied into frontend/host/src/components/ImageThumb.tsx (the apps share no code) — keep
 * the two in sync.
 */
import { useEffect, useState } from 'react';
import { ImageOff } from 'lucide-react';
import { loadImageUrl } from '../lib/images';
import { cn } from '../lib/utils';

interface ImageThumbProps {
  imageId: number;
  alt: string;
  className?: string;
}

export function ImageThumb({ imageId, alt, className }: ImageThumbProps) {
  const [state, setState] = useState<{ id: number; url: string | null; failed: boolean }>({
    id: imageId,
    url: null,
    failed: false,
  });

  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;
    setState({ id: imageId, url: null, failed: false });
    loadImageUrl(imageId)
      .then((u) => {
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        url = u;
        setState({ id: imageId, url: u, failed: false });
      })
      .catch(() => {
        if (!cancelled) setState({ id: imageId, url: null, failed: true });
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [imageId]);

  return (
    <div
      className={cn(
        'flex items-center justify-center overflow-hidden rounded-md bg-slate-900/60',
        className,
      )}
    >
      {state.url ? (
        <img src={state.url} alt={alt} className="h-full w-full object-contain" />
      ) : state.failed ? (
        <span className="flex flex-col items-center gap-1 text-xs text-slate-400">
          <ImageOff size={18} aria-hidden="true" />
          Image unavailable
        </span>
      ) : (
        <span className="text-xs text-slate-500">Loading…</span>
      )}
    </div>
  );
}
