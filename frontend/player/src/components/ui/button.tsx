import { cn } from '../../lib/utils';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost' | 'destructive';
  size?: 'sm' | 'md' | 'lg';
}

/** Riso Press button (docs/plans/t9-theming.md §7.1): ink outline and a hard shadow that the
 * button presses down into. Focus uses the global :focus-visible outline. */
export function Button({ className, variant = 'default', size = 'md', ...props }: ButtonProps) {
  const pressable = variant !== 'ghost';
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-xl font-bold transition-[transform,box-shadow,background-color] duration-75',
        'disabled:opacity-50 disabled:pointer-events-none disabled:shadow-none',
        pressable && 'border-2 border-line shadow-hard active:translate-x-1 active:translate-y-1 active:shadow-none',
        variant === 'default' && 'bg-accent text-on-fill',
        variant === 'outline' && 'bg-surface text-ink hover:bg-sunken',
        variant === 'ghost' && 'bg-transparent text-ink-muted hover:bg-sunken hover:text-ink',
        variant === 'destructive' && 'bg-danger text-on-fill',
        size === 'sm' && 'px-3 py-2 text-sm',
        size === 'md' && 'px-5 py-3 text-base',
        size === 'lg' && 'px-6 py-4 text-lg',
        className
      )}
      {...props}
    />
  );
}
