import { cn } from '../../lib/utils';

type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'w-full rounded-lg border border-line bg-surface px-3 py-2',
        'text-ink placeholder:text-ink-soft',
        'focus:outline-none focus:ring-[3px] focus:ring-focus',
        className
      )}
      {...props}
    />
  );
}
