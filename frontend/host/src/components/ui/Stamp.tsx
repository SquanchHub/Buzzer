import { cn } from '../../lib/utils';

export type StampTone = 'success' | 'warning' | 'danger' | 'accent';

// Static map so Tailwind sees every class (docs/plans/t9-theming.md D10a).
const TONE: Record<StampTone, string> = {
  success: 'text-success-ink',
  warning: 'text-warning-ink',
  danger: 'text-danger-ink',
  accent: 'text-accent-ink',
};

/** A rubber-stamp verdict (S3): a word, never colour alone. */
export function Stamp({
  tone,
  className,
  children,
  ...props
}: { tone: StampTone } & React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        'inline-block -rotate-6 select-none rounded-md border-[3px] border-current px-4 py-1',
        'font-mono font-black uppercase tracking-widest',
        'outline outline-1 outline-current -outline-offset-[7px]',
        TONE[tone],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}
