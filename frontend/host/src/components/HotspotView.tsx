import { useEffect, useRef, useState } from 'react';
import { loadImageUrl } from '../lib/images';
import { HOTSPOT_TAP_CAP, type HotspotBand, type HotspotTap } from '../types/game';

/*
 * The host's hotspot display (docs/plans/t7-hotspot.md §7.6, §7.8): image, optional
 * target rings, optional taps coloured by band, optional legend. Display only.
 *
 * Same layout rule as the player's HotspotCanvas (the apps share no code — keep the
 * two in step): the image is letterboxed by aspectRatio so layout is fixed before it
 * loads; points are fractions of the image; ring radii are fractions of the image's
 * longer side, drawn as true circles — the circle the server scores against.
 */

export interface HotspotRings {
  x: number;
  y: number;
  innerRadius: number;
  outerRadius: number;
}

type ImageState = { status: 'loading' } | { status: 'ready'; url: string } | { status: 'error' };

function useImageUrl(imageId: number | undefined): ImageState {
  const [image, setImage] = useState<ImageState>({ status: 'loading' });
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

// Colours come from CSS variables so theming (T9) reaches the canvas; fallbacks until then.
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

const BAND_LABELS: Record<HotspotBand, string> = { inner: 'Bullseye', outer: 'Close', miss: 'Miss' };

/** Rings from a hotspot reveal, or null (COMPLETENESS / invalid stored target, §5.4). */
export function ringsFromReveal(reveal: { type?: string; x?: number; y?: number; innerRadius?: number; outerRadius?: number }): HotspotRings | null {
  if (reveal.type !== 'hotspot') return null;
  const { x, y, innerRadius, outerRadius } = reveal;
  if (x === undefined || y === undefined || innerRadius === undefined || outerRadius === undefined) return null;
  return { x, y, innerRadius, outerRadius };
}

interface HotspotViewProps {
  imageId: number | undefined;
  aspectRatio: number;
  label: string;
  rings?: HotspotRings | null;
  taps?: HotspotTap[];
  /** Legend: band counts under ACCURACY, tap count under COMPLETENESS. Omit for no legend. */
  legend?: { accuracy: boolean; distribution: Record<string, number> };
  maxHeightVh?: number;
}

export function HotspotView({
  imageId,
  aspectRatio,
  label,
  rings = null,
  taps = [],
  legend,
  maxHeightVh = 55,
}: HotspotViewProps) {
  const image = useImageUrl(imageId);
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [imgEl, setImgEl] = useState<HTMLImageElement | null>(null);
  const aspect = aspectRatio > 0 && Number.isFinite(aspectRatio) ? aspectRatio : 1;

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

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !size || size.w === 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(size.w * dpr);
    canvas.height = Math.round(size.h * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const imgW = Math.min(size.w, size.h * aspect);
    const imgH = imgW / aspect;
    const imgX = (size.w - imgW) / 2;
    const imgY = (size.h - imgH) / 2;

    ctx.clearRect(0, 0, size.w, size.h);
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(imgX, imgY, imgW, imgH);
    if (imgEl) {
      ctx.drawImage(imgEl, imgX, imgY, imgW, imgH);
    } else {
      ctx.fillStyle = '#94a3b8';
      ctx.font = '600 20px system-ui, sans-serif';
      ctx.textAlign = 'center';
      if (image.status === 'error') {
        // Bottom edge, so rings and taps drawn over the blank box don't cover it.
        ctx.textBaseline = 'bottom';
        ctx.fillText('Image unavailable', imgX + imgW / 2, imgY + imgH - 12);
      } else {
        ctx.textBaseline = 'middle';
        ctx.fillText('Loading image…', imgX + imgW / 2, imgY + imgH / 2);
      }
    }

    const longer = Math.max(imgW, imgH);
    const toX = (x: number) => imgX + x * imgW;
    const toY = (y: number) => imgY + y * imgH;

    if (rings) {
      ctx.lineWidth = 3;
      ctx.setLineDash([10, 7]);
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

    for (const t of taps) {
      ctx.beginPath();
      ctx.arc(toX(t.x), toY(t.y), 6, 0, Math.PI * 2);
      ctx.fillStyle = colour(t.band ?? 'neutral');
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = '#0f172a';
      ctx.stroke();
    }
  }, [size, imgEl, image.status, aspect, rings, taps]);

  let legendText: React.ReactNode = null;
  if (legend) {
    if (legend.accuracy) {
      legendText = (Object.keys(BAND_LABELS) as HotspotBand[]).map((band, i) => (
        <span key={band}>
          {i > 0 && <span className="text-slate-600"> · </span>}
          <span style={{ color: colour(band) }}>●</span> {BAND_LABELS[band]} {legend.distribution[band] ?? 0}
        </span>
      ));
    } else {
      // COMPLETENESS records no band counts; the tap list is capped server-side.
      const n = taps.length;
      legendText = n >= HOTSPOT_TAP_CAP ? `${HOTSPOT_TAP_CAP}+ taps` : `${n} tap${n === 1 ? '' : 's'}`;
    }
  }

  return (
    <div ref={wrapRef} className="w-full">
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={label}
        style={{ width: size ? `${size.w}px` : '100%', height: size ? `${size.h}px` : undefined }}
        className="block rounded-xl bg-slate-900"
      />
      {legendText && <p className="mt-3 text-center text-slate-300 text-lg">{legendText}</p>}
    </div>
  );
}
