import { Stamp } from '../../components/ui/Stamp';

export default function FeedbackPage() {
  return (
    <div className="min-h-[calc(100dvh-3rem)] flex flex-col items-center justify-center p-6 gap-6 text-center">
      <Stamp tone="accent" className="text-3xl">Locked in</Stamp>
      <p className="font-display text-ink text-2xl font-extrabold">Answer locked in!</p>
      <div className="flex gap-2" aria-hidden>
        <span className="h-3 w-3 rounded-full bg-accent animate-bounce [animation-delay:-0.3s]" />
        <span className="h-3 w-3 rounded-full bg-accent animate-bounce [animation-delay:-0.15s]" />
        <span className="h-3 w-3 rounded-full bg-accent animate-bounce" />
      </div>
      <p className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-ink-muted">Waiting for the host to reveal results…</p>
    </div>
  );
}
