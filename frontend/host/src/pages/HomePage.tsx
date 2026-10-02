import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';

interface Course { id: number; name: string; semester: string }
interface Game { id: number; title: string; course_id: number | null }
interface ActiveSession {
  session_id: string;
  room_code: string;
  status: string;
  game_title: string;
  course_name: string;
  course_semester: string;
}

export default function HomePage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [activeSessions, setActiveSessions] = useState<ActiveSession[]>([]);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [courseId, setCourseId] = useState<number | ''>('');
  const [gameId, setGameId] = useState<number | ''>('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      api.get<Course[]>('/game/my-courses'),
      api.get<Game[]>('/game/my-games'),
      api.get<ActiveSession[]>('/game/my-active-sessions'),
    ]).then(([c, g, s]) => {
      setCourses(c);
      setGames(g);
      setActiveSessions(s);
      if (c.length === 1) setCourseId(c[0].id);
    }).catch(() => setError('Failed to load courses or games. Are you still logged in?'));
  }, []);

  // A game runs only in its own course (T4 D4), so the quiz list follows the selected
  // course; unassigned games (course_id null) never match and stay hidden.
  const courseGames = courseId === '' ? [] : games.filter(g => g.course_id === courseId);
  useEffect(() => {
    setGameId(courseGames.length === 1 ? courseGames[0].id : '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, games]);

  async function deleteSession(sessionId: string) {
    try {
      await api.delete(`/game/sessions/${sessionId}`);
      setActiveSessions(prev => prev.filter(s => s.session_id !== sessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete session');
    } finally {
      setConfirmDelete(null);
    }
  }

  async function createRoom() {
    if (!courseId || !gameId) return;
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ room_code: string }>('/game/rooms', {
        course_id: courseId,
        game_id: gameId,
      });
      navigate(`/game/${data.room_code}/lobby`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create room');
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-center gap-4">
      {activeSessions.length > 0 && (
        <Card className="w-full max-w-lg border-amber-500/40">
          <CardHeader>
            <h2 className="text-lg font-semibold text-amber-400">Active Sessions</h2>
            <p className="text-slate-400 text-sm">You have running games — rejoin one or create a new room below.</p>
          </CardHeader>
          <CardContent className="space-y-2">
            {activeSessions.map(s => (
              <div
                key={s.session_id}
                className="flex items-center justify-between rounded-lg bg-slate-800 border border-slate-700 px-4 py-3"
              >
                <div>
                  <p className="text-slate-100 font-medium">{s.game_title}</p>
                  <p className="text-slate-400 text-sm">{s.course_name} · {s.course_semester}</p>
                  <p className="text-slate-500 text-xs mt-0.5">
                    Room <span className="font-mono text-slate-300">{s.room_code}</span>
                    {' · '}
                    <span className={s.status === 'IN_PROGRESS' ? 'text-green-400' : 'text-amber-400'}>
                      {s.status === 'IN_PROGRESS' ? 'In Progress' : 'Lobby'}
                    </span>
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {confirmDelete === s.session_id ? (
                    <>
                      <span className="text-red-400 text-xs">Delete all data?</span>
                      <Button size="sm" variant="destructive" onClick={() => deleteSession(s.session_id)}>
                        Confirm
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(null)}>
                        Cancel
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button size="sm" variant="outline" onClick={() => navigate(`/game/${s.room_code}/lobby`)}>
                        Rejoin
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => setConfirmDelete(s.session_id)}>
                        Delete
                      </Button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card className="w-full max-w-lg">
        <CardHeader>
          <h1 className="text-2xl font-bold text-slate-100">Create Game Room</h1>
          <p className="text-slate-400 text-sm mt-1">Select a course and quiz to begin</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Course</label>
            <select
              value={courseId}
              onChange={e => setCourseId(Number(e.target.value))}
              className="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Select a course…</option>
              {courses.map(c => (
                <option key={c.id} value={c.id}>{c.name} — {c.semester}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Quiz</label>
            <select
              value={gameId}
              onChange={e => setGameId(Number(e.target.value))}
              className="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">{courseId === '' ? 'Select a course first' : 'Select a quiz…'}</option>
              {courseGames.map(g => (
                <option key={g.id} value={g.id}>{g.title}</option>
              ))}
            </select>
          </div>
          {courseId !== '' && courseGames.length === 0 && (
            <p className="text-slate-500 text-sm">
              No quizzes you can run in this course yet — create one from the course page below.
            </p>
          )}
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <Button
            className="w-full"
            size="lg"
            onClick={createRoom}
            disabled={!courseId || !gameId || loading}
          >
            {loading ? 'Creating room…' : 'Create Room'}
          </Button>
        </CardContent>
      </Card>

      {courses.length > 0 && (
        <section className="w-full max-w-lg">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-2">Your courses</h2>
          <div className="space-y-2">
            {courses.map(c => (
              <Link
                key={c.id}
                to={`/courses/${c.id}`}
                className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-3 hover:border-indigo-500 hover:bg-slate-800 transition-colors"
              >
                <div>
                  <p className="text-slate-100 font-medium">{c.name}</p>
                  <p className="text-slate-400 text-sm">{c.semester}</p>
                </div>
                <span className="text-indigo-400 text-sm">Games &amp; roster →</span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
