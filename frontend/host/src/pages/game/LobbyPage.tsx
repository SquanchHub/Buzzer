import { QRCodeSVG } from 'qrcode.react';
import { Users } from 'lucide-react';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import { Ticket } from '../../components/ui/Ticket';
import { cn } from '../../lib/utils';

export default function LobbyPage() {
  const { roomCode, gameTitle, playerCount, emitAdvance, autoAdvance, setAutoAdvance } = useGame();

  const playerJoinUrl = `${window.location.origin}/player/join?code=${roomCode}`;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 gap-10">
      {/* Quiz name */}
      <div className="flex flex-col items-center gap-3 text-center">
        {gameTitle && (
          <h1 className="font-display text-5xl font-extrabold tracking-tight text-ink max-w-4xl leading-tight">
            {gameTitle}
          </h1>
        )}
        {/* Join instructions */}
        <p className="font-mono text-lg font-bold uppercase tracking-[0.2em] text-ink-muted">
          Scan or go to <span className="text-ink underline decoration-accent decoration-4 underline-offset-4">{window.location.host}/player</span>
        </p>
      </div>

      {/* QR code + room code side by side */}
      <div className="flex flex-wrap items-center justify-center gap-12">
        <div className="rounded-3xl border-2 border-line bg-qr p-5 shadow-hard-lg">
          <QRCodeSVG value={playerJoinUrl} size={220} />
        </div>
        <Ticket code={roomCode} size="lg" />
      </div>

      {/* Player count */}
      <div className="flex items-center gap-4 rounded-full border-2 border-line bg-surface px-6 py-2 shadow-hard">
        <Users className="h-7 w-7 text-accent-ink" aria-hidden />
        {playerCount === 0 ? (
          <p className="font-mono text-xl font-bold uppercase tracking-[0.15em] text-ink-muted">
            Waiting for players to join…
          </p>
        ) : (
          <p className="text-2xl font-bold text-ink-muted">
            <span className="font-mono text-4xl font-extrabold text-ink">{playerCount}</span>{' '}
            player{playerCount !== 1 ? 's' : ''} joined
          </p>
        )}
      </div>

      {/* Auto-advance switch, in the theme toggle's pill language */}
      <button
        type="button"
        role="switch"
        aria-checked={autoAdvance}
        className="flex items-center gap-3 group rounded-full"
        onClick={() => setAutoAdvance(!autoAdvance)}
      >
        <span
          className={cn(
            'relative h-8 w-14 rounded-full border-2 border-line transition-colors',
            autoAdvance ? 'bg-accent' : 'bg-sunken'
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 h-6 w-6 rounded-full border-2 border-line bg-surface transition-transform',
              autoAdvance ? 'translate-x-6' : 'translate-x-0.5'
            )}
          />
        </span>
        <span className="text-ink-muted text-base font-semibold group-hover:text-ink transition-colors select-none">
          Auto-advance — run game hands-free
        </span>
      </button>

      {/* Start button */}
      <Button size="lg" onClick={emitAdvance} disabled={playerCount === 0} className="px-14 text-xl">
        {playerCount === 0 ? 'Waiting for players…' : 'Start Game'}
      </Button>
    </div>
  );
}
