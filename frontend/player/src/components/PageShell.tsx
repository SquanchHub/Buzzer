import { ThemeToggle } from './ThemeToggle';

/** Frame for the pre-game pages (join, name, sign-in return): the wordmark and the theme
 * switch on top, the content centred in the thumb-friendly lower part of the screen. */
export function PageShell({ children, hero = false }: { children: React.ReactNode; hero?: boolean }) {
  return (
    <div className="min-h-[100dvh] flex flex-col px-4 pb-6 pt-3">
      <header className="flex items-center justify-between">
        {!hero ? (
          <span className="font-display text-2xl font-extrabold tracking-tight text-ink">
            buzzer<span className="text-accent">.</span>
          </span>
        ) : <span />}
        <ThemeToggle />
      </header>
      {hero && (
        <div className="mt-10 text-center">
          <p className="font-display text-7xl font-extrabold leading-none tracking-tighter text-ink [text-shadow:4px_4px_0_rgb(var(--accent))]">
            buzzer
          </p>
          <p className="mt-4 font-mono text-[11px] font-bold uppercase tracking-[0.35em] text-ink-soft">
            the classroom quiz show
          </p>
        </div>
      )}
      <main className="flex flex-1 flex-col items-center justify-center py-6">{children}</main>
    </div>
  );
}
