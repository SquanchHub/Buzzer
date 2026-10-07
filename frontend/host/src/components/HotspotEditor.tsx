import { useEffect, useRef, useState, type ReactNode } from 'react';
import { loadImageUrl } from '../lib/images';
import { cssColor, useTheme } from '../lib/theme';
import { cn } from '../lib/utils';
import { Input } from './ui/input';

/*
 * Authoring panel for a hotspot question (docs/plans/t7-hotspot.md §7.9, §13.2): pick the
 * image, click the preview to place the target centre, and set the inner/outer radii and the
 * partial-credit fraction. Rings are drawn live with the same layout rule scoring uses (§7.6).
 *
 * Self-contained on purpose: it imports only lib/images.ts, lib/theme.ts, lib/utils.ts and components/ui/*,
 * so T4 phase 3 copies it into frontend/admin/src/components/ with import-path changes only
 * (H9) — keep the two copies in sync. The image loading and letterbox maths repeat
 * HotspotView's (the editor may not import it) — keep those in step too.
 *
 * Image-ready signal (§13.2 G4): config.aspectRatio is sent only once the current imageId's
 * image has loaded, and is dropped whenever imageId changes (including on mount, for a stored
 * question), so the page can enable Save on "aspectRatio is a number" without guessing it.
 */

export interface HotspotEditorConfig {
  imageId?: number;
  aspectRatio?: number;
}

export interface HotspotEditorTarget {
  x: number;
  y: number;
  innerRadius: number;
  outerRadius: number;
  partialFraction: number;
}

/** Defaults for a new hotspot question (§7.9). */
export const HOTSPOT_DEFAULT_TARGET: HotspotEditorTarget = {
  x: 0.5,
  y: 0.5,
  innerRadius: 0.03,
  outerRadius: 0.08,
  partialFraction: 0.5,
};

/** The server's aspectRatio range (§5.1); an image outside it can't be saved. */
export const HOTSPOT_ASPECT_MIN = 0.2;
export const HOTSPOT_ASPECT_MAX = 5;

const INNER_MIN = 0.02;
const INNER_MAX = 0.5;
const RADIUS_STEP = 0.005;

interface HotspotEditorProps {
  config: HotspotEditorConfig;
  answerData: HotspotEditorTarget;
  onChange: (config: HotspotEditorConfig, answerData: HotspotEditorTarget) => void;
  /** Slot for T8's image picker; without it the editor shows a numeric Image ID field. */
  renderImagePicker?: (imageId: number | undefined, setImageId: (id: number | undefined) => void) => ReactNode;
}

type ImageState =
  | { status: 'none' }
  | { status: 'loading' }
  | { status: 'ready'; img: HTMLImageElement; aspect: number }
  | { status: 'error' };

/** Click coordinates and slider values are stored to 4 decimal places (under a pixel). */
const round4 = (v: number) => Math.round(v * 1e4) / 1e4;

// Canvas colours are read from the theme tokens at draw time (docs/plans/t9-theming.md §6);
// the draw effect depends on the theme so a toggle repaints.
const RING_TOKEN = { inner: '--success', outer: '--warning' } as const;

function colour(name: keyof typeof RING_TOKEN): string {
  return cssColor(RING_TOKEN[name]);
}

function isValidAspect(a: number | undefined): a is number {
  return typeof a === 'number' && Number.isFinite(a) && a > 0;
}

export function HotspotEditor({ config, answerData, onChange, renderImagePicker }: HotspotEditorProps) {
  const imageId = config.imageId;
  // The latest props, for callbacks that outlive the render they were created in.
  const latest = useRef({ config, answerData, onChange });
  latest.current = { config, answerData, onChange };

  const [image, setImage] = useState<ImageState>({ status: 'none' });
  // Layout aspect while no image is loaded: the stored one at first, then the last loaded one,
  // so the preview doesn't jump while the next image loads.
  const lastAspect = useRef<number>(isValidAspect(config.aspectRatio) ? config.aspectRatio : 1);
  const [idText, setIdText] = useState(imageId === undefined ? '' : String(imageId));

  function setImageId(id: number | undefined) {
    // A new image: drop aspectRatio until it has loaded (G4).
    latest.current.onChange(id === undefined ? {} : { imageId: id }, latest.current.answerData);
  }

  function setTarget(patch: Partial<HotspotEditorTarget>) {
    latest.current.onChange(latest.current.config, { ...latest.current.answerData, ...patch });
  }

  useEffect(() => {
    if (latest.current.config.aspectRatio !== undefined) {
      latest.current.onChange(imageId === undefined ? {} : { imageId }, latest.current.answerData);
    }
    if (imageId === undefined) {
      setImage({ status: 'none' });
      return;
    }
    let cancelled = false;
    let url: string | null = null;
    const el = new Image();
    setImage({ status: 'loading' });
    loadImageUrl(imageId)
      .then((u) => {
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        url = u;
        el.onload = () => {
          if (cancelled) return;
          const aspect = el.naturalWidth / el.naturalHeight;
          lastAspect.current = aspect;
          setImage({ status: 'ready', img: el, aspect });
          latest.current.onChange({ imageId, aspectRatio: aspect }, latest.current.answerData);
        };
        el.onerror = () => {
          if (!cancelled) setImage({ status: 'error' });
        };
        el.src = u;
      })
      .catch(() => {
        if (!cancelled) setImage({ status: 'error' });
      });
    return () => {
      cancelled = true;
      el.onload = null;
      el.onerror = null;
      if (url) URL.revokeObjectURL(url);
    };
  }, [imageId]);

  // ---- preview canvas (same layout rule as HotspotView, §7.6) ----
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const aspect = image.status === 'ready' ? image.aspect : lastAspect.current;

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const measure = () => {
      const w = wrap.clientWidth;
      const h = Math.min(w / aspect, window.innerHeight * 0.5);
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
  }, [aspect]);

  /** The drawn image's box inside the canvas, in CSS px. */
  function imageBox(s: { w: number; h: number }) {
    const imgW = Math.min(s.w, s.h * aspect);
    const imgH = imgW / aspect;
    return { imgX: (s.w - imgW) / 2, imgY: (s.h - imgH) / 2, imgW, imgH };
  }

  const { x, y, innerRadius, outerRadius, partialFraction } = answerData;

  const [theme] = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !size || size.w === 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(size.w * dpr);
    canvas.height = Math.round(size.h * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const { imgX, imgY, imgW, imgH } = imageBox(size);

    ctx.clearRect(0, 0, size.w, size.h);
    ctx.fillStyle = cssColor('--sunken');
    ctx.fillRect(imgX, imgY, imgW, imgH);
    if (image.status === 'ready') {
      ctx.drawImage(image.img, imgX, imgY, imgW, imgH);
    } else {
      ctx.fillStyle = cssColor('--ink-soft');
      ctx.font = "600 16px 'Bricolage Grotesque Variable', system-ui, sans-serif";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const text =
        image.status === 'loading' ? 'Loading image…'
        : image.status === 'error' ? 'Image unavailable'
        : 'Choose an image';
      ctx.fillText(text, imgX + imgW / 2, imgY + imgH / 2);
      return; // no target over a missing image
    }

    const longer = Math.max(imgW, imgH);
    const cx = imgX + x * imgW;
    const cy = imgY + y * imgH;
    ctx.lineWidth = 3;
    ctx.setLineDash([10, 7]);
    ctx.strokeStyle = colour('outer');
    ctx.beginPath();
    ctx.arc(cx, cy, outerRadius * longer, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.strokeStyle = colour('inner');
    ctx.beginPath();
    ctx.arc(cx, cy, innerRadius * longer, 0, Math.PI * 2);
    ctx.stroke();
    // Centre crosshair, outlined so it shows on light and dark images.
    for (const [width, stroke] of [[4, cssColor('--on-fill')], [2, cssColor('--canvas')]] as const) {
      ctx.lineWidth = width;
      ctx.strokeStyle = stroke;
      ctx.beginPath();
      ctx.moveTo(cx - 8, cy);
      ctx.lineTo(cx + 8, cy);
      ctx.moveTo(cx, cy - 8);
      ctx.lineTo(cx, cy + 8);
      ctx.stroke();
    }
  }, [size, image, aspect, x, y, innerRadius, outerRadius, theme]);

  function placeCentre(e: React.MouseEvent<HTMLCanvasElement>) {
    if (image.status !== 'ready' || !size) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const { imgX, imgY, imgW, imgH } = imageBox(size);
    const fx = (e.clientX - rect.left - imgX) / imgW;
    const fy = (e.clientY - rect.top - imgY) / imgH;
    if (fx < 0 || fx > 1 || fy < 0 || fy > 1) return; // a click in the letterbox bars
    setTarget({ x: round4(fx), y: round4(fy) });
  }

  const outOfRangeAspect =
    image.status === 'ready' && (image.aspect < HOTSPOT_ASPECT_MIN || image.aspect > HOTSPOT_ASPECT_MAX)
      ? image.aspect
      : null;
  const pct = (r: number) => `${(r * 100).toFixed(1)}% of longer side`;

  return (
    <div className="space-y-3">
      <div>
        {renderImagePicker ? (
          renderImagePicker(imageId, setImageId)
        ) : (
          <label className="block text-xs text-ink-muted">
            Image ID
            <Input
              type="number"
              min="1"
              step="1"
              value={idText}
              onChange={(e) => {
                setIdText(e.target.value);
                const n = Number(e.target.value);
                setImageId(e.target.value !== '' && Number.isInteger(n) && n > 0 ? n : undefined);
              }}
              className="mt-1 w-32 text-sm"
            />
          </label>
        )}
        {image.status === 'error' && (
          <p className="mt-1 text-xs text-danger-ink">Image {imageId} is unavailable; choose another image.</p>
        )}
        {outOfRangeAspect !== null && (
          <p className="mt-1 text-xs text-danger-ink">
            This image's aspect ratio ({outOfRangeAspect.toFixed(2)}) is outside {HOTSPOT_ASPECT_MIN}–{HOTSPOT_ASPECT_MAX};
            choose another image.
          </p>
        )}
      </div>

      <div ref={wrapRef} className="w-full">
        <canvas
          ref={canvasRef}
          role="img"
          aria-label="Hotspot preview: click the image to place the target centre"
          onClick={placeCentre}
          style={{ width: size ? `${size.w}px` : '100%', height: size ? `${size.h}px` : undefined }}
          className={cn('block rounded-lg ring-2 ring-line bg-canvas', image.status === 'ready' && 'cursor-crosshair')}
        />
        <p className="mt-1 text-xs text-ink-soft">
          {image.status === 'ready'
            ? `Click the image to place the target centre — currently (${x.toFixed(4)}, ${y.toFixed(4)}).`
            : 'The target can be placed once the image has loaded.'}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block text-xs text-ink-muted">
          Inner radius (full points): <span className="text-ink">{pct(innerRadius)}</span>
          <input
            type="range"
            min={INNER_MIN}
            max={INNER_MAX}
            step={RADIUS_STEP}
            value={innerRadius}
            onChange={(e) => {
              const inner = round4(Number(e.target.value));
              // Keep inner ≤ outer: raising inner past outer pushes outer up with it.
              setTarget({ innerRadius: inner, outerRadius: Math.max(outerRadius, inner) });
            }}
            className="mt-1 w-full accent-accent"
          />
        </label>
        <label className="block text-xs text-ink-muted">
          Outer radius (partial points): <span className="text-ink">{pct(outerRadius)}</span>
          <input
            type="range"
            min={innerRadius}
            max={1}
            step={RADIUS_STEP}
            value={outerRadius}
            onChange={(e) => setTarget({ outerRadius: Math.max(innerRadius, round4(Number(e.target.value))) })}
            className="mt-1 w-full accent-accent"
          />
        </label>
        <label className="block text-xs text-ink-muted">
          Partial credit: <span className="text-ink">{Math.round(partialFraction * 100)}% of points</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={partialFraction}
            onChange={(e) => setTarget({ partialFraction: Math.round(Number(e.target.value) * 100) / 100 })}
            className="mt-1 w-full accent-accent"
          />
        </label>
      </div>
    </div>
  );
}
