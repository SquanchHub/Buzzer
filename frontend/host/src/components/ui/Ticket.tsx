import { cn } from '../../lib/utils';

const SIZE = {
  lg: { box: 'px-14 py-6', code: 'text-[7.5rem] leading-none', eyebrow: 'text-sm' },
  md: { box: 'px-10 py-4', code: 'text-5xl', eyebrow: 'text-xs' },
  sm: { box: 'px-5 py-1.5', code: 'text-lg', eyebrow: 'text-[9px]' },
} as const;

/** The room code printed on a ticket stub (S4): notched sides, a perforation and a hard
 * shadow, all following the notch shape (`.ticket-frame` / `.ticket` in index.css). */
export function Ticket({
  code,
  size = 'md',
  className,
}: {
  code: string;
  size?: keyof typeof SIZE;
  className?: string;
}) {
  const s = SIZE[size];
  return (
    <div className={cn('ticket-frame inline-block', className)}>
      <div className={cn('ticket bg-surface text-center', s.box)}>
        <p className={cn('font-mono font-bold uppercase tracking-[0.35em] text-ink-soft', s.eyebrow)}>
          Room
        </p>
        <div className="my-1 border-t-2 border-dashed border-line-soft" aria-hidden />
        <p className={cn('font-mono font-extrabold tracking-[0.12em] text-ink', s.code)} data-testid="room-code">
          {code}
        </p>
      </div>
    </div>
  );
}
