import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, List, Upload, Trash2, Pencil } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Input } from '../components/ui/input';

interface Game {
  id: number;
  title: string;
  description: string;
  max_players: number;
  course_id: number | null;
  created_at: string;
}

interface Course {
  id: number;
  name: string;
  semester: string;
}

const selectClass =
  'w-full rounded-lg border border-line bg-surface px-3 py-2 text-ink focus:outline-none focus:ring-[3px] focus:ring-focus focus:border-transparent';

export default function GamesPage() {
  const [games, setGames] = useState<Game[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [maxPlayers, setMaxPlayers] = useState('150');
  const [courseId, setCourseId] = useState('');
  const [importCourseId, setImportCourseId] = useState('');
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [editingGame, setEditingGame] = useState<Game | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editMaxPlayers, setEditMaxPlayers] = useState('');
  const [editCourseId, setEditCourseId] = useState('');
  const [editError, setEditError] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  // 'all', 'unassigned', or a course id.
  const [filter, setFilter] = useState('all');
  const fileRef = useRef<HTMLInputElement>(null);
  const editRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  async function load() {
    try {
      const [data, courseData] = await Promise.all([
        api.get<Game[]>('/admin/games'),
        api.get<Course[]>('/admin/courses'),
      ]);
      setGames(data);
      setCourses(courseData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load games');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  // The edit form sits above the list, so bring it into view (the list can be long).
  useEffect(() => {
    if (!editingGame) return;
    editRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    editRef.current?.querySelector('input')?.focus({ preventScroll: true });
  }, [editingGame]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await api.post('/admin/games', {
        title,
        description,
        max_players: Number(maxPlayers),
        course_id: Number(courseId),
      });
      setTitle(''); setDescription(''); setMaxPlayers('150'); setCourseId('');
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create game');
    } finally {
      setSaving(false);
    }
  }

  function startEdit(g: Game) {
    setEditingGame(g);
    setEditTitle(g.title);
    setEditDescription(g.description);
    setEditMaxPlayers(String(g.max_players));
    setEditCourseId(g.course_id === null ? '' : String(g.course_id));
    setEditError('');
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingGame) return;
    setEditSaving(true);
    setEditError('');
    try {
      await api.put(`/admin/games/${editingGame.id}`, {
        title: editTitle,
        description: editDescription,
        max_players: Number(editMaxPlayers),
        // Only sent when moving; the API refuses null and a move while live (409).
        ...(editCourseId && Number(editCourseId) !== editingGame.course_id
          ? { course_id: Number(editCourseId) }
          : {}),
      });
      setEditingGame(null);
      await load();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Failed to update game');
    } finally {
      setEditSaving(false);
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('course_id', importCourseId);
      const result = await api.postForm<{ game_id: number }>('/admin/games/import', form);
      await load();
      navigate(`/games/${result.game_id}/questions`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  function courseLabel(id: number | null): string {
    if (id === null) return 'Unassigned';
    const c = courses.find((x) => x.id === id);
    return c ? `${c.name} (${c.semester})` : `Course ${id}`;
  }

  const visibleGames = games.filter((g) =>
    filter === 'all' ? true : filter === 'unassigned' ? g.course_id === null : g.course_id === Number(filter),
  );

  async function deleteGame(id: number) {
    if (!confirm('Delete this game and all its sessions? This cannot be undone.')) return;
    try {
      await api.delete(`/admin/games/${id}`);
      setGames((prev) => prev.filter((g) => g.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete game');
    }
  }

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-display text-3xl font-extrabold tracking-tight text-ink">Games</h2>
        <div className="flex gap-2">
          <select
            aria-label="Course to import into"
            value={importCourseId}
            onChange={(e) => setImportCourseId(e.target.value)}
            className="rounded-lg border border-line bg-surface px-2 py-1 text-sm text-ink focus:outline-none focus:ring-[3px] focus:ring-focus"
          >
            <option value="">Import into course{'\u2026'}</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>{c.name} ({c.semester})</option>
            ))}
          </select>
          <input ref={fileRef} type="file" accept=".json" className="hidden" onChange={handleImport} />
          <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={importing || !importCourseId}
            title={importCourseId ? undefined : 'Choose a course to import into first'}>
            <Upload size={14} className="mr-1" />
            {importing ? 'Importing\u2026' : 'Import JSON'}
          </Button>
          <Button size="sm" onClick={() => setShowForm(!showForm)}>
            <Plus size={16} className="mr-1" /> New Game
          </Button>
        </div>
      </div>

      {error && <p className="text-danger-ink mb-4 text-sm">{error}</p>}

      {showForm && (
        <Card className="mb-6">
          <CardHeader><h3 className="font-display text-lg font-extrabold text-ink">Create Game</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="space-y-3">
              <Input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} required />
              <div>
                <label htmlFor="create-course" className="block text-xs text-ink-muted mb-1">Course</label>
                <select
                  id="create-course"
                  value={courseId}
                  onChange={(e) => setCourseId(e.target.value)}
                  className={selectClass}
                  required
                >
                  <option value="">Choose a course{'\u2026'}</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>{c.name} ({c.semester})</option>
                  ))}
                </select>
              </div>
              <textarea
                placeholder="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-ink placeholder:text-ink-soft focus:outline-none focus:ring-[3px] focus:ring-focus focus:border-transparent resize-none"
                rows={3}
              />
              <div>
                <label className="block text-xs text-ink-muted mb-1">Max players</label>
                <Input
                  type="number"
                  value={maxPlayers}
                  onChange={(e) => setMaxPlayers(e.target.value)}
                  min="1"
                  max="500"
                />
              </div>
              <div className="flex gap-3">
                <Button type="submit" disabled={saving}>{saving ? 'Creating\u2026' : 'Create'}</Button>
                <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {editingGame && (
        <div ref={editRef} className="scroll-mt-4">
        <Card className="mb-6">
          <CardHeader><h3 className="font-display text-lg font-extrabold text-ink">Edit Game</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleEdit} className="space-y-3">
              <Input placeholder="Title" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} required />
              <textarea
                placeholder="Description (optional)"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
                className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-ink placeholder:text-ink-soft focus:outline-none focus:ring-[3px] focus:ring-focus focus:border-transparent resize-none"
                rows={3}
              />
              <div>
                <label htmlFor="edit-course" className="block text-xs text-ink-muted mb-1">Course</label>
                <select
                  id="edit-course"
                  value={editCourseId}
                  onChange={(e) => setEditCourseId(e.target.value)}
                  className={selectClass}
                >
                  {editingGame.course_id === null && <option value="">Unassigned — choose a course…</option>}
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>{c.name} ({c.semester})</option>
                  ))}
                </select>
                <p className="text-xs text-ink-soft mt-1">
                  Moving a game doesn't change the course of sessions already played.
                </p>
              </div>
              <div>
                <label className="block text-xs text-ink-muted mb-1">Max players</label>
                <Input
                  type="number"
                  value={editMaxPlayers}
                  onChange={(e) => setEditMaxPlayers(e.target.value)}
                  min="1"
                  max="500"
                />
              </div>
              {editError && <p className="text-danger-ink text-sm">{editError}</p>}
              <div className="flex gap-3">
                <Button type="submit" disabled={editSaving}>{editSaving ? 'Saving\u2026' : 'Save'}</Button>
                <Button type="button" variant="ghost" onClick={() => setEditingGame(null)}>Cancel</Button>
              </div>
            </form>
          </CardContent>
        </Card>
        </div>
      )}

      <div className="flex items-center gap-2 mb-4">
        <label htmlFor="course-filter" className="text-xs text-ink-muted">Show</label>
        <select
          id="course-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded-lg border border-line bg-surface px-2 py-1 text-sm text-ink focus:outline-none focus:ring-[3px] focus:ring-focus"
        >
          <option value="all">All courses</option>
          <option value="unassigned">Unassigned ({games.filter((g) => g.course_id === null).length})</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>{c.name} ({c.semester})</option>
          ))}
        </select>
      </div>

      {loading ? (
        <p className="text-ink-muted">Loading…</p>
      ) : visibleGames.length === 0 ? (
        <p className="text-ink-muted">{games.length === 0 ? 'No games yet.' : 'No games match this filter.'}</p>
      ) : (
        <div className="space-y-3">
          {visibleGames.map((g) => (
            <Card key={g.id} className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="font-semibold text-ink">{g.title}</p>
                {g.description && <p className="text-ink-muted text-sm mt-0.5 line-clamp-1">{g.description}</p>}
                <p className="text-ink-soft text-xs mt-0.5">
                  {g.course_id === null ? (
                    <span className="text-warning-ink">Unassigned — edit to choose a course</span>
                  ) : (
                    <Link to={`/courses/${g.course_id}`} className="hover:underline">{courseLabel(g.course_id)}</Link>
                  )}
                  {' · '}Max {g.max_players} players
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => startEdit(g)}
                >
                  <Pencil size={14} />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/games/${g.id}/questions`)}
                >
                  <List size={14} className="mr-1" /> Questions
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => void deleteGame(g.id)}
                >
                  <Trash2 size={14} />
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
