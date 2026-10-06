import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Gamepad2, Trash2, UserPlus, Users } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Input } from '../components/ui/input';

interface Course {
  id: number;
  name: string;
  semester: string;
}

interface Member {
  user_id: string;
  username: string | null;
  display_name: string | null;
  netid: string | null;
  role: 'HOST' | 'PLAYER';
}

interface UserRow {
  id: string;
  username: string | null;
  display_name: string | null;
  netid: string | null;
  role: string;
}

interface Game {
  id: number;
  title: string;
  course_id: number | null;
}

const selectClass =
  'rounded-lg border border-slate-600 bg-slate-800 px-2 py-1.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500';

function label(u: { display_name: string | null; username: string | null; netid: string | null }) {
  return u.display_name || u.username || u.netid || 'Unnamed user';
}

// Under D1 a host's game grants only work while they HOST the game's course.
const HOST_LOSS_WARNING =
  'They will lose access to every game in this course until HOST is granted again (their game grants are kept). Continue?';

export default function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const [course, setCourse] = useState<Course | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState('');
  const [semester, setSemester] = useState('');
  const [saving, setSaving] = useState(false);
  const [newUserId, setNewUserId] = useState('');
  const [newRole, setNewRole] = useState<'HOST' | 'PLAYER'>('HOST');
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [c, m, u, g] = await Promise.all([
        api.get<Course>(`/admin/courses/${courseId}`),
        api.get<Member[]>(`/admin/courses/${courseId}/access`),
        api.get<UserRow[]>('/admin/users'),
        api.get<Game[]>('/admin/games'),
      ]);
      setCourse(c);
      setName(c.name);
      setSemester(c.semester);
      setMembers(m);
      setUsers(u);
      setGames(g.filter((x) => x.course_id === c.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load course');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [courseId]);

  async function rename(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      setCourse(await api.put<Course>(`/admin/courses/${courseId}`, { name, semester }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to rename course');
    } finally {
      setSaving(false);
    }
  }

  async function run(action: () => Promise<unknown>, failure: string) {
    setBusy(true);
    setError('');
    try {
      await action();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : failure);
    } finally {
      setBusy(false);
    }
  }

  function setRole(m: Member, role: 'HOST' | 'PLAYER') {
    if (role === m.role) return;
    if (m.role === 'HOST' && !confirm(`Make ${label(m)} a PLAYER? ${HOST_LOSS_WARNING}`)) return;
    void run(
      () => api.post(`/admin/users/${m.user_id}/course-access`, { course_id: Number(courseId), role }),
      'Failed to change role',
    );
  }

  function revoke(m: Member) {
    const extra = m.role === 'HOST' ? ` ${HOST_LOSS_WARNING}` : '';
    if (!confirm(`Remove ${label(m)} from this course?${extra}`)) return;
    void run(
      () => api.delete(`/admin/users/${m.user_id}/course-access/${courseId}`),
      'Failed to remove member',
    );
  }

  function addMember(e: React.FormEvent) {
    e.preventDefault();
    if (!newUserId) return;
    void run(async () => {
      await api.post(`/admin/users/${newUserId}/course-access`, {
        course_id: Number(courseId),
        role: newRole,
      });
      setNewUserId('');
    }, 'Failed to add member');
  }

  if (loading) return <p className="p-8 text-slate-400">Loading…</p>;
  if (!course) {
    return (
      <div className="p-8">
        <p className="text-red-400 text-sm">{error || 'Course not found'}</p>
        <Link to="/courses" className="text-indigo-400 text-sm hover:underline">Back to courses</Link>
      </div>
    );
  }

  const memberIds = new Set(members.map((m) => m.user_id));
  // Admins bypass course roles, so only USER accounts are worth adding.
  const candidates = users.filter((u) => u.role === 'USER' && !memberIds.has(u.id));

  return (
    <div className="p-8 max-w-4xl space-y-6">
      <div>
        <Link to="/courses" className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-slate-200">
          <ArrowLeft size={14} /> Courses
        </Link>
        <div className="mt-2 flex items-center justify-between">
          <h2 className="text-2xl font-bold text-slate-100">
            {course.name} <span className="text-slate-400 font-normal">({course.semester})</span>
          </h2>
          <Link to={`/courses/${course.id}/roster`}>
            <Button variant="outline" size="sm"><Users size={14} className="mr-1" /> Roster</Button>
          </Link>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <Card>
        <CardHeader><h3 className="text-lg font-semibold text-slate-100">Details</h3></CardHeader>
        <CardContent>
          <form onSubmit={rename} className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-48">
              <label htmlFor="course-name" className="block text-xs text-slate-400 mb-1">Name</label>
              <Input id="course-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="w-40">
              <label htmlFor="course-semester" className="block text-xs text-slate-400 mb-1">Semester</label>
              <Input id="course-semester" value={semester} onChange={(e) => setSemester(e.target.value)} required />
            </div>
            <Button type="submit" disabled={saving || (name === course.name && semester === course.semester)}>
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h3 className="text-lg font-semibold text-slate-100">Members</h3>
          <p className="text-xs text-slate-400 mt-1">
            HOSTs can run this course's games they've been granted, and manage its roster and games
            in the Host app. Students on the roster can join without a role here.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {members.length === 0 ? (
            <p className="text-slate-400 text-sm">No hosts or players yet.</p>
          ) : (
            <ul className="divide-y divide-slate-700">
              {members.map((m) => (
                <li key={m.user_id} className="flex items-center justify-between py-2 gap-3">
                  <Link to={`/users/${m.user_id}`} className="text-slate-100 hover:underline">
                    {label(m)}
                    {m.username && m.display_name && (
                      <span className="text-slate-500 text-xs ml-2">@{m.username}</span>
                    )}
                  </Link>
                  <div className="flex items-center gap-2">
                    <select
                      aria-label={`Role of ${label(m)}`}
                      value={m.role}
                      disabled={busy}
                      onChange={(e) => setRole(m, e.target.value as 'HOST' | 'PLAYER')}
                      className={selectClass}
                    >
                      <option value="HOST">HOST</option>
                      <option value="PLAYER">PLAYER</option>
                    </select>
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={busy}
                      onClick={() => revoke(m)}
                      aria-label={`Remove ${label(m)}`}
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={addMember} className="flex flex-wrap gap-2 items-center pt-2 border-t border-slate-700">
            <select
              aria-label="User to add"
              value={newUserId}
              onChange={(e) => setNewUserId(e.target.value)}
              className={`${selectClass} flex-1 min-w-48`}
            >
              <option value="">Add a user…</option>
              {candidates.map((u) => (
                <option key={u.id} value={u.id}>{label(u)}{u.username ? ` (@${u.username})` : ''}</option>
              ))}
            </select>
            <select
              aria-label="Role for the new member"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as 'HOST' | 'PLAYER')}
              className={selectClass}
            >
              <option value="HOST">HOST</option>
              <option value="PLAYER">PLAYER</option>
            </select>
            <Button type="submit" size="sm" disabled={busy || !newUserId}>
              <UserPlus size={14} className="mr-1" /> Add
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><h3 className="text-lg font-semibold text-slate-100">Games</h3></CardHeader>
        <CardContent>
          {games.length === 0 ? (
            <p className="text-slate-400 text-sm">
              No games in this course yet. Create or import one on the <Link to="/games" className="text-indigo-400 hover:underline">Games</Link> page.
            </p>
          ) : (
            <ul className="space-y-1">
              {games.map((g) => (
                <li key={g.id}>
                  <Link to={`/games/${g.id}/questions`} className="inline-flex items-center gap-2 text-slate-100 hover:underline">
                    <Gamepad2 size={14} className="text-slate-400" /> {g.title}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
