import { cn } from '../../lib/utils';

type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'w-full rounded-xl border-2 border-line bg-surface px-4 py-3 text-base',
        'text-ink placeholder:text-ink-soft',
        'focus:outline-none focus:ring-[3px] focus:ring-focus',
        className
      )}
      {...props}
    />
  );
}
