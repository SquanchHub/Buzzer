import { Moon, Sun } from 'lucide-react';
import { cn } from '../lib/utils';
import { useTheme } from '../lib/theme';

interface ThemeToggleProps {
  /** Icon only (game screens). */
  compact?: boolean;
  /** Inverted colours for a `bg-ink` slab (admin sidebar). */
  onSlab?: boolean;
  className?: string;
}

/** The "Paper / Night" switch (docs/plans/t9-theming.md §5.3). Identical in all three apps. */
export function ThemeToggle({ compact = false, onSlab = false, className }: ThemeToggleProps) {
  const [theme, setTheme] = useTheme();
  const dark = theme === 'dark';
  const half = (active: boolean) =>
    cn(
      'flex items-center justify-center gap-1.5 rounded-full px-2.5 py-1 transition-colors',
      active
        ? onSlab ? 'bg-canvas text-ink' : 'bg-ink text-canvas'
        : onSlab ? 'text-canvas/70' : 'text-ink-soft'
    );
  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label="Dark theme"
      title={dark ? 'Switch to Paper (light)' : 'Switch to Night (dark)'}
      data-testid="theme-toggle"
      onClick={() => setTheme(dark ? 'light' : 'dark')}
      className={cn(
        'inline-flex min-h-[44px] items-center rounded-full border-2 p-1 font-mono text-[11px] font-bold uppercase tracking-widest',
        onSlab ? 'border-canvas bg-ink' : 'border-line bg-surface shadow-hard-sm',
        compact && 'min-w-[44px] justify-center',
        className
      )}
    >
      {compact ? (
        <span className={half(true)}>
          {dark ? <Moon className="h-4 w-4" aria-hidden /> : <Sun className="h-4 w-4" aria-hidden />}
        </span>
      ) : (
        <>
          <span className={half(!dark)}>
            <Sun className="h-3.5 w-3.5" aria-hidden />
            Paper
          </span>
          <span className={half(dark)}>
            <Moon className="h-3.5 w-3.5" aria-hidden />
            Night
          </span>
        </>
      )}
    </button>
  );
}
