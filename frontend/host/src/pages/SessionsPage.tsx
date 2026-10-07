import { useEffect, useState } from 'react';
import { Download, FileText } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';

/** MySessionItem from GET /game/my-sessions (T4 §6.2.4). */
interface Session {
  session_id: string;
  room_code: string;
  game_title: string;
  course_name: string;
  course_semester: string;
  completed_at: string | null;
  player_count: number;
}

type Kind = 'report' | 'export';

/** The host's completed sessions with their downloads (T4 §6.3, D9). */
export default function SessionsPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<string | null>(null); // `${session_id}:${kind}`
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null);

  useEffect(() => {
    api.get<Session[]>('/game/my-sessions')
      .then(setSessions)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load sessions'))
      .finally(() => setLoading(false));
  }, []);

  async function download(s: Session, kind: Kind) {
    setRowError(null);
    setBusy(`${s.session_id}:${kind}`);
    try {
      // fetch + blob: an <a href> can't send the bearer token.
      await api.download(`/game/sessions/${s.session_id}/${kind}`);
    } catch (err) {
      setRowError({ id: s.session_id, message: err instanceof Error ? err.message : 'Download failed' });
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <p className="text-center text-ink-muted">Loading sessions…</p>;

  return (
    <div className="mx-auto max-w-3xl">
      <Card>
        <CardHeader>
          <h1 className="font-display text-3xl font-extrabold tracking-tight text-ink">Completed sessions</h1>
          <p className="text-ink-muted text-sm mt-1">Games you hosted that have finished, newest first.</p>
        </CardHeader>
        <CardContent className="space-y-2">
          {error && <p className="text-sm text-danger-ink">{error}</p>}
          {!error && sessions.length === 0 && (
            <p className="text-ink-muted text-sm">No completed sessions yet. They appear here once a game you host reaches the final results.</p>
          )}
          {sessions.map((s) => (
            <div key={s.session_id} className="rounded-lg border border-line-soft bg-surface px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-ink">{s.game_title}</p>
                  <p className="text-sm text-ink-muted">{s.course_name} · {s.course_semester}</p>
                  <p className="text-xs text-ink-soft mt-0.5">
                    {s.completed_at ? new Date(s.completed_at).toLocaleString() : 'Completed'}
                    {' · '}{s.player_count} player{s.player_count === 1 ? '' : 's'}
                    {' · '}Room <span className="font-mono text-ink-muted">{s.room_code}</span>
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => download(s, 'report')}>
                    <FileText size={14} className="mr-1" />
                    {busy === `${s.session_id}:report` ? 'Downloading…' : 'Download summary (HTML)'}
                  </Button>
                  <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => download(s, 'export')}>
                    <Download size={14} className="mr-1" />
                    {busy === `${s.session_id}:export` ? 'Downloading…' : 'Download scores (CSV)'}
                  </Button>
                </div>
              </div>
              {rowError?.id === s.session_id && <p className="mt-2 text-sm text-danger-ink">{rowError.message}</p>}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
