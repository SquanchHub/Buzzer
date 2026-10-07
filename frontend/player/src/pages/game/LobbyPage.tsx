import { useGame } from './GameLayout';
import { Stamp } from '../../components/ui/Stamp';
import { Ticket } from '../../components/ui/Ticket';

export default function LobbyPage() {
  const { roomCode, playerCount, gameStatus } = useGame();

  const statusText = gameStatus === 'IN_PROGRESS'
    ? 'Waiting for next question…'
    : 'Waiting for host to start…';

  return (
    <div className="min-h-[calc(100dvh-3rem)] flex flex-col items-center justify-center p-6 gap-8 text-center">
      <Stamp tone="success" className="text-2xl">You're in</Stamp>
      <Ticket code={roomCode} size="md" />
      <div className="space-y-3">
        <div className="flex justify-center gap-2" aria-hidden>
          <span className="h-3 w-3 rounded-full bg-accent animate-bounce [animation-delay:-0.3s]" />
          <span className="h-3 w-3 rounded-full bg-accent animate-bounce [animation-delay:-0.15s]" />
          <span className="h-3 w-3 rounded-full bg-accent animate-bounce" />
        </div>
        <p className="font-display text-ink text-xl font-bold">{statusText}</p>
        <p className="inline-flex items-center gap-2 rounded-full border-2 border-line bg-surface px-4 py-1 font-mono text-sm font-bold text-ink-muted">
          <span className="text-ink">{playerCount}</span> player{playerCount !== 1 ? 's' : ''} in room
        </p>
      </div>
    </div>
  );
}
