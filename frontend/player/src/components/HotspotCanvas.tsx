import { useEffect, useRef, useState } from 'react';
import { loadImageUrl } from '../lib/images';
import type { HotspotBand, HotspotPoint } from '../types/game';

/*
 * The player's hotspot canvas (docs/plans/t7-hotspot.md §7.6–7.7).
 *
 * Layout rule shared by every hotspot canvas: the image is letterboxed inside the
 * canvas using config.aspectRatio, so the layout is fixed before the image loads.
 * Points are fractions of the image (0..1 from the top-left). A ring radius is a
 * fraction of the image's longer side, so it is drawn as a true circle — the same
 * circle the server scores against.
 */

export type HotspotImage =
  | { status: 'loading' }
  | { status: 'ready'; url: string }
  | { status: 'error' };

export interface HotspotRings {
  x: number;
  y: number;
  innerRadius: number;
  outerRadius: number;
}

/** Load an image for a display canvas; revokes the object URL on change/unmount. */
export function useImageUrl(imageId: number | undefined): HotspotImage {
  const [image, setImage] = useState<HotspotImage>({ status: 'loading' });
  useEffect(() => {
    if (typeof imageId !== 'number') {
      setImage({ status: 'error' });
      return;
    }
    let cancelled = false;
    let url: string | null = null;
    setImage({ status: 'loading' });
    loadImageUrl(imageId)
      .then((u) => {
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        url = u;
        setImage({ status: 'ready', url: u });
      })
      .catch(() => {
        if (!cancelled) setImage({ status: 'error' });
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [imageId]);
  return image;
}

// Colours come from CSS variables so theming (T9) reaches the canvas; these are
// the fallbacks until T9 defines them.
const FALLBACK_COLOURS = {
  inner: '#4ade80',
  outer: '#fbbf24',
  miss: '#f87171',
  neutral: '#94a3b8',
} as const;

function colour(name: keyof typeof FALLBACK_COLOURS): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--hotspot-${name}`).trim();
  return v || FALLBACK_COLOURS[name];
}

interface Layout {
  w: number; // canvas CSS size
  h: number;
  imgX: number; // drawn image rect inside the canvas, CSS px
  imgY: number;
  imgW: number;
  imgH: number;
}

function letterbox(w: number, h: number, aspect: number): Layout {
  const imgW = Math.min(w, h * aspect);
  const imgH = imgW / aspect;
  return { w, h, imgX: (w - imgW) / 2, imgY: (h - imgH) / 2, imgW, imgH };
}

interface HotspotCanvasProps {
  aspectRatio: number;
  image: HotspotImage;
  /** aria-label, e.g. the prompt. */
  label: string;
  /** Interactive: taps on the image call onPick; taps in the letterbox are ignored. */
  interactive?: boolean;
  onPick?: (point: HotspotPoint) => void;
  /** The player's own point (placed or submitted), coloured by band when known. */
  marker?: (HotspotPoint & { band?: HotspotBand | null }) | null;
  rings?: HotspotRings | null;
  /** Height cap as a percentage of the viewport height. */
  maxHeightVh?: number;
}

export function HotspotCanvas({
  aspectRatio,
  image,
  label,
  interactive = false,
  onPick,
  marker = null,
  rings = null,
  maxHeightVh = 60,
}: HotspotCanvasProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [imgEl, setImgEl] = useState<HTMLImageElement | null>(null);
  const aspect = aspectRatio > 0 && Number.isFinite(aspectRatio) ? aspectRatio : 1;

  // Size: full container width; height from the aspect ratio, capped by maxHeightVh.
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const measure = () => {
      const w = wrap.clientWidth;
      const h = Math.min(w / aspect, (window.innerHeight * maxHeightVh) / 100);
      setSize((prev) => (prev && prev.w === w && prev.h === h ? prev : { w, h }));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(wrap);
    window.addEventListener('resize', measure);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [aspect, maxHeightVh]);

  // Decode the image once its URL is ready.
  const url = image.status === 'ready' ? image.url : null;
  useEffect(() => {
    setImgEl(null);
    if (!url) return;
    const el = new Image();
    el.onload = () => setImgEl(el);
    el.src = url;
    return () => {
      el.onload = null;
    };
  }, [url]);

  // Draw.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !size || size.w === 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(size.w * dpr);
    canvas.height = Math.round(size.h * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const L = letterbox(size.w, size.h, aspect);

    ctx.clearRect(0, 0, L.w, L.h);
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(L.imgX, L.imgY, L.imgW, L.imgH);
    if (imgEl) {
      ctx.drawImage(imgEl, L.imgX, L.imgY, L.imgW, L.imgH);
    } else {
      ctx.fillStyle = '#94a3b8';
      ctx.font = '600 16px system-ui, sans-serif';
      ctx.textAlign = 'center';
      if (image.status === 'error') {
        // Bottom edge, so rings and taps drawn over the blank box don't cover it.
        ctx.textBaseline = 'bottom';
        ctx.fillText('Image unavailable', L.imgX + L.imgW / 2, L.imgY + L.imgH - 10);
      } else {
        ctx.textBaseline = 'middle';
        ctx.fillText('Loading image…', L.imgX + L.imgW / 2, L.imgY + L.imgH / 2);
      }
    }

    const longer = Math.max(L.imgW, L.imgH);
    const toX = (x: number) => L.imgX + x * L.imgW;
    const toY = (y: number) => L.imgY + y * L.imgH;

    if (rings) {
      ctx.lineWidth = 2.5;
      ctx.setLineDash([8, 6]);
      ctx.strokeStyle = colour('outer');
      ctx.beginPath();
      ctx.arc(toX(rings.x), toY(rings.y), rings.outerRadius * longer, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.strokeStyle = colour('inner');
      ctx.beginPath();
      ctx.arc(toX(rings.x), toY(rings.y), rings.innerRadius * longer, 0, Math.PI * 2);
      ctx.stroke();
    }

    if (marker) {
      const fill = marker.band ? colour(marker.band) : '#818cf8';
      ctx.beginPath();
      ctx.arc(toX(marker.x), toY(marker.y), 8, 0, Math.PI * 2);
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.lineWidth = 3;
      ctx.strokeStyle = '#ffffff';
      ctx.stroke();
    }
  }, [size, imgEl, image.status, aspect, rings, marker]);

  function handlePointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!interactive || !onPick || !size) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const L = letterbox(size.w, size.h, aspect);
    const x = (e.clientX - rect.left - L.imgX) / L.imgW;
    const y = (e.clientY - rect.top - L.imgY) / L.imgH;
    if (x < 0 || x > 1 || y < 0 || y > 1) return; // letterbox area
    onPick({ x, y });
  }

  return (
    <div ref={wrapRef} className="w-full">
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={label}
        onPointerDown={handlePointerDown}
        style={{
          width: size ? `${size.w}px` : '100%',
          height: size ? `${size.h}px` : undefined,
          touchAction: interactive ? 'none' : undefined,
          cursor: interactive ? 'crosshair' : undefined,
        }}
        className="block rounded-xl bg-slate-900"
      />
    </div>
  );
}
