import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Download, Image as ImageIcon, Pencil, Plus, Trash2, Upload, Users } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Input } from '../components/ui/input';

interface Course { id: number; name: string; semester: string }

/** HostGameItem from GET /host/courses/:id/games (T4 §6.2.3). */
interface Game {
  id: number;
  title: string;
  description: string;
  max_players: number;
  course_id: number | null;
  session_count: number;
}

// Links styled like <Button variant="outline" size="sm"> (a <button> inside an <a> is invalid).
const linkButton =
  'inline-flex items-center justify-center rounded-lg font-semibold transition-colors border border-line-soft text-ink hover:bg-sunken focus:outline-none focus:ring-2 focus:ring-focus focus:ring-offset-2 focus:ring-offset-canvas px-3 py-1.5 text-sm';

/** The delete confirmation names what is lost (T4 §6.3, D6). */
function deletePrompt(g: Game): string {
  if (g.session_count === 0) return `Delete '${g.title}'?`;
  const sessions = g.session_count === 1 ? '1 session' : `${g.session_count} sessions`;
  return `Delete '${g.title}'? This permanently deletes its ${sessions} and all their scores.`;
}

export default function CoursePage() {
  const { courseId } = useParams<{ courseId: string }>();
  const id = Number(courseId);
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);

  const [course, setCourse] = useState<Course | null>(null);
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [maxPlayers, setMaxPlayers] = useState('150');
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [rowError, setRowError] = useState<{ id: number; message: string } | null>(null);

  async function load() {
    try {
      const [courses, list] = await Promise.all([
        api.get<Course[]>('/game/my-courses'),
        api.get<Game[]>(`/host/courses/${id}/games`),
      ]);
      setCourse(courses.find((c) => c.id === id) ?? null);
      setGames(list);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load the course');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [id]);

  async function createGame(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const game = await api.post<{ id: number }>('/host/games', {
        title,
        description,
        max_players: Number(maxPlayers),
        course_id: id,
      });
      navigate(`/games/${game.id}/edit`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create the game');
      setBusy(false);
    }
  }

  async function importGame(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-picking the same file
    if (!file) return;
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('course_id', String(id));
      const result = await api.postForm<{ game_id: number }>('/host/games/import', form);
      navigate(`/games/${result.game_id}/edit`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
      setBusy(false);
    }
  }

  async function exportGame(g: Game) {
    setRowError(null);
    try {
      await api.download(`/host/games/${g.id}/export`);
    } catch (err) {
      setRowError({ id: g.id, message: err instanceof Error ? err.message : 'Export failed' });
    }
  }

  async function deleteGame(g: Game) {
    setRowError(null);
    try {
      await api.delete(`/host/games/${g.id}`);
      setGames((prev) => prev.filter((x) => x.id !== g.id));
    } catch (err) {
      // e.g. 409 "This game has a live session" — shown on the row, not as a page takeover.
      setRowError({ id: g.id, message: err instanceof Error ? err.message : 'Delete failed' });
    } finally {
      setConfirmDelete(null);
    }
  }

  if (loading) return <p className="text-center text-ink-muted">Loading course…</p>;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to="/home" className="text-sm text-ink-muted hover:text-ink">← Home</Link>
          <h1 className="font-display text-3xl font-extrabold tracking-tight text-ink">{course ? course.name : `Course ${id}`}</h1>
          {course && <p className="text-ink-muted text-sm">{course.semester}</p>}
        </div>
        <div className="flex gap-2">
          <Link to={`/courses/${id}/images`} className={linkButton}>
            <ImageIcon size={14} className="mr-1" />Images
          </Link>
          <Link to={`/courses/${id}/roster`} className={linkButton}>
            <Users size={14} className="mr-1" />Roster
          </Link>
        </div>
      </div>

      {error && <p className="rounded-lg border border-danger bg-danger/15 px-4 py-2 text-sm text-danger-ink">{error}</p>}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-display text-xl font-extrabold text-ink">Games</h2>
            <div className="flex gap-2">
              <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={importGame} />
              <Button variant="outline" size="sm" disabled={busy} onClick={() => fileRef.current?.click()}>
                <Upload size={14} className="mr-1" />Import JSON
              </Button>
              <Button size="sm" disabled={busy} onClick={() => setShowCreate((v) => !v)}>
                <Plus size={14} className="mr-1" />New game
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {showCreate && (
            <form onSubmit={createGame} className="space-y-2 rounded-lg border border-line-soft p-3">
              <Input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={255} />
              <textarea
                placeholder="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={5000}
                rows={2}
                className="w-full rounded-lg border border-line-soft bg-surface px-3 py-2 text-ink placeholder:text-ink-soft focus:outline-none focus:ring-2 focus:ring-focus"
              />
              <label className="flex items-center gap-2 text-sm text-ink-muted">
                Max players
                <Input type="number" min={1} max={500} value={maxPlayers} onChange={(e) => setMaxPlayers(e.target.value)} className="w-28" />
              </label>
              <div className="flex gap-2">
                <Button type="submit" disabled={busy || !title.trim()}>Create and edit questions</Button>
                <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
              </div>
            </form>
          )}

          {games.length === 0 && !showCreate && (
            <p className="text-ink-muted text-sm">No games you can run in this course yet. Create one or import a JSON file.</p>
          )}

          {games.map((g) => (
            <div key={g.id} className="rounded-lg border border-line-soft bg-surface px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium text-ink">{g.title}</p>
                  <p className="text-xs text-ink-muted">
                    {g.session_count === 1 ? '1 session' : `${g.session_count} sessions`} · Max {g.max_players} players
                  </p>
                </div>
                {confirmDelete === g.id ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-danger-ink">{deletePrompt(g)}</span>
                    <Button size="sm" variant="destructive" onClick={() => deleteGame(g)}>Delete</Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(null)}>Cancel</Button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <Link to={`/games/${g.id}/edit`} className={linkButton}>
                      <Pencil size={14} className="mr-1" />Edit
                    </Link>
                    <Button size="sm" variant="outline" onClick={() => exportGame(g)} aria-label={`Export ${g.title}`}>
                      <Download size={14} />
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => { setRowError(null); setConfirmDelete(g.id); }} aria-label={`Delete ${g.title}`}>
                      <Trash2 size={14} />
                    </Button>
                  </div>
                )}
              </div>
              {rowError?.id === g.id && <p className="mt-2 text-sm text-danger-ink">{rowError.message}</p>}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
