import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Trash2, Pencil } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Input } from '../components/ui/input';

interface CourseAccess { course_id: number; role: string }
interface UserDetail {
  id: string;
  username: string | null;
  netid: string | null;
  display_name: string | null;
  email: string | null;
  role: string;
  created_at: string;
  last_login: string | null;
  course_access: CourseAccess[];
  game_access: number[];
}
interface Course { id: number; name: string; semester: string }
interface Game { id: number; title: string; course_id: number | null }

interface CourseSelection { id: number; role: 'HOST' | 'PLAYER'; checked: boolean }
interface GameSelection { id: number; checked: boolean }

export default function UserDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<UserDetail | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [error, setError] = useState('');
  const [showCoursePanel, setShowCoursePanel] = useState(false);
  const [courseSelections, setCourseSelections] = useState<CourseSelection[]>([]);
  const [grantingCourses, setGrantingCourses] = useState(false);
  const [showGamePanel, setShowGamePanel] = useState(false);
  const [gameSelections, setGameSelections] = useState<GameSelection[]>([]);
  const [grantingGames, setGrantingGames] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editUsername, setEditUsername] = useState('');
  const [editDisplayName, setEditDisplayName] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editPassword, setEditPassword] = useState('');
  const [editRole, setEditRole] = useState('');
  const [editSaving, setEditSaving] = useState(false);

  async function load() {
    try {
      const [u, cs, gs] = await Promise.all([
        api.get<UserDetail>(`/admin/users/${userId}`),
        api.get<Course[]>('/admin/courses'),
        api.get<Game[]>('/admin/games'),
      ]);
      setUser(u);
      setCourses(cs);
      setGames(gs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load user');
    }
  }

  useEffect(() => { void load(); }, [userId]);

  function openCoursePanel(availableCourses: Course[]) {
    setCourseSelections(availableCourses.map((c) => ({ id: c.id, role: 'HOST', checked: false })));
    setShowCoursePanel(true);
  }

  async function grantSelectedCourses() {
    const selected = courseSelections.filter((s) => s.checked);
    if (selected.length === 0) return;
    setGrantingCourses(true);
    setError('');
    try {
      await Promise.all(
        selected.map((s) => api.post(`/admin/users/${userId}/course-access`, { course_id: s.id, role: s.role }))
      );
      setShowCoursePanel(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to grant access');
    } finally {
      setGrantingCourses(false);
    }
  }

  async function revokeCourseAccess(courseId: number) {
    try {
      await api.delete(`/admin/users/${userId}/course-access/${courseId}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke access');
    }
  }

  function openGamePanel(availableGames: Game[]) {
    setGameSelections(availableGames.map((g) => ({ id: g.id, checked: false })));
    setShowGamePanel(true);
  }

  async function grantSelectedGames() {
    const selected = gameSelections.filter((s) => s.checked);
    if (selected.length === 0) return;
    setGrantingGames(true);
    setError('');
    // One at a time, so each refusal (e.g. the 409 "must have HOST access to this
    // game's course") is reported against its game while the others still go through.
    const failures: string[] = [];
    for (const s of selected) {
      try {
        await api.post(`/admin/users/${userId}/game-access`, { game_id: s.id });
      } catch (err) {
        const title = games.find((g) => g.id === s.id)?.title ?? `Game ${s.id}`;
        failures.push(`${title}: ${err instanceof Error ? err.message : 'failed'}`);
      }
    }
    if (failures.length === 0) setShowGamePanel(false);
    else setError(`Some games were not granted. ${failures.join(' · ')}`);
    await load();
    setGrantingGames(false);
  }

  async function revokeGameAccess(gameId: number) {
    try {
      await api.delete(`/admin/users/${userId}/game-access/${gameId}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke game access');
    }
  }

  function startEdit(u: UserDetail) {
    setEditUsername(u.username ?? '');
    setEditDisplayName(u.display_name ?? '');
    setEditEmail(u.email ?? '');
    setEditPassword('');
    setEditRole(u.role);
    setEditing(true);
  }

  async function saveEdit() {
    if (!user) return;
    setEditSaving(true);
    setError('');
    try {
      const body: Record<string, string> = {};
      if (user.username !== null && editUsername !== user.username) body.username = editUsername;
      if (editDisplayName !== (user.display_name ?? '')) body.display_name = editDisplayName;
      if (editEmail !== (user.email ?? '')) body.email = editEmail;
      if (editPassword) body.password = editPassword;
      if (editRole !== user.role) body.role = editRole;
      await api.put(`/admin/users/${userId}`, body);
      setEditing(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update user');
    } finally {
      setEditSaving(false);
    }
  }

  async function deleteUser() {
    if (!confirm('Delete this user? This cannot be undone.')) return;
    try {
      await api.delete(`/admin/users/${userId}`);
      navigate('/users');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete user');
    }
  }

  if (!user) return <div className="p-8 text-ink-muted">{error || 'Loading\u2026'}</div>;

  const courseMap = Object.fromEntries(courses.map((c) => [c.id, c]));
  const gameMap = Object.fromEntries(games.map((g) => [g.id, g]));

  const grantedCourseIds = new Set(user.course_access.map((ca) => ca.course_id));
  const grantedGameIds = new Set(user.game_access);
  const availableCourses = courses.filter((c) => !grantedCourseIds.has(c.id));
  const availableGames = games.filter((g) => !grantedGameIds.has(g.id));

  // D1: a non-admin's game grant only works while they HOST the game's course.
  const hostedCourseIds = new Set(
    user.course_access.filter((ca) => ca.role === 'HOST').map((ca) => ca.course_id),
  );
  const canUseGame = (g: Game | undefined) =>
    user.role === 'ADMIN' || (g !== undefined && g.course_id !== null && hostedCourseIds.has(g.course_id));
  const courseName = (id: number | null) =>
    id === null ? 'Unassigned' : courseMap[id] ? `${courseMap[id].name} (${courseMap[id].semester})` : `Course ${id}`;
  // Picker groups: one per course (plus Unassigned), in course-list order.
  const gameGroups = [...courses.map((c) => c.id as number | null), null]
    .map((cid) => ({
      courseId: cid,
      selections: gameSelections
        .map((sel, index) => ({ sel, index }))
        .filter(({ sel }) => (gameMap[sel.id]?.course_id ?? null) === cid),
    }))
    .filter((group) => group.selections.length > 0);

  const selectedCourseCount = courseSelections.filter((s) => s.checked).length;
  const selectedGameCount = gameSelections.filter((s) => s.checked).length;

  return (
    <div className="p-8 max-w-3xl space-y-6">
      <button
        onClick={() => navigate('/users')}
        className="flex items-center gap-2 text-ink-muted hover:text-ink text-sm"
      >
        <ArrowLeft size={14} /> Back to Users
      </button>

      {error && <p className="text-danger-ink text-sm">{error}</p>}

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <h2 className="font-display text-2xl font-extrabold tracking-tight text-ink">{user.display_name ?? user.username ?? user.netid}</h2>
              <p className="text-ink-muted text-sm mt-0.5">
                {user.username && <span className="mr-3">@{user.username}</span>}
                {user.netid && <span className="mr-3">netid: {user.netid}</span>}
                <span className="px-2 py-0.5 rounded-full text-xs bg-sunken text-ink-muted">{user.role}</span>
              </p>
            </div>
            <div className="flex gap-2">
              {!editing && (
                <Button variant="outline" size="sm" onClick={() => startEdit(user)}>
                  <Pencil size={14} className="mr-1" /> Edit
                </Button>
              )}
              {user.role !== 'ADMIN' && (
                <Button variant="destructive" size="sm" onClick={() => void deleteUser()}>
                  <Trash2 size={14} className="mr-1" /> Delete
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {editing ? (
            <div className="space-y-3 pt-1">
              {user.username !== null && (
                <div>
                  <label className="block text-xs text-ink-muted mb-1">Username</label>
                  <Input
                    value={editUsername}
                    onChange={(e) => setEditUsername(e.target.value)}
                    placeholder="username"
                    className="text-sm"
                  />
                </div>
              )}
              <div>
                <label className="block text-xs text-ink-muted mb-1">Display name</label>
                <Input
                  value={editDisplayName}
                  onChange={(e) => setEditDisplayName(e.target.value)}
                  placeholder="Display name"
                  className="text-sm"
                />
              </div>
              <div>
                <label className="block text-xs text-ink-muted mb-1">Email</label>
                <Input
                  type="email"
                  value={editEmail}
                  onChange={(e) => setEditEmail(e.target.value)}
                  placeholder="email@example.com"
                  className="text-sm"
                />
              </div>
              {user.username !== null && (
                <div>
                  <label className="block text-xs text-ink-muted mb-1">New password <span className="text-ink-soft">(leave blank to keep current)</span></label>
                  <Input
                    type="password"
                    value={editPassword}
                    onChange={(e) => setEditPassword(e.target.value)}
                    placeholder="New password"
                    className="text-sm"
                  />
                </div>
              )}
              <div>
                <label className="block text-xs text-ink-muted mb-1">Role</label>
                <select
                  className="rounded-lg border border-line bg-surface px-3 py-2 text-ink text-sm"
                  value={editRole}
                  onChange={(e) => setEditRole(e.target.value)}
                >
                  <option value="USER">USER</option>
                  <option value="ADMIN">ADMIN</option>
                </select>
              </div>
              <div className="flex gap-2 pt-1">
                <Button size="sm" onClick={() => void saveEdit()} disabled={editSaving}>
                  {editSaving ? 'Saving\u2026' : 'Save'}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <div className="space-y-1">
              {user.email && <p className="text-ink-muted text-xs">{user.email}</p>}
              {user.netid && <p className="text-ink-soft text-xs">netid: {user.netid} (OAuth2 — not editable)</p>}
              <p className="text-ink-soft text-xs">
                Created {new Date(user.created_at).toLocaleDateString()}
                {user.last_login && ` \u00b7 Last login ${new Date(user.last_login).toLocaleDateString()}`}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Course access */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h3 className="font-display text-lg font-extrabold text-ink">Course Access</h3>
            {availableCourses.length > 0 && !showCoursePanel && (
              <Button size="sm" variant="outline" onClick={() => openCoursePanel(availableCourses)}>
                Add Courses
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {user.course_access.length === 0 && !showCoursePanel && (
            <p className="text-ink-soft text-sm">No course access granted.</p>
          )}
          {user.course_access.map((ca) => {
            const course = courseMap[ca.course_id];
            return (
              <div key={ca.course_id} className="flex items-center justify-between">
                <span className="text-ink text-sm">
                  {course ? `${course.name} \u2014 ${course.semester}` : `Course ${ca.course_id}`}
                  <span className="ml-2 text-xs text-ink-muted">{ca.role}</span>
                </span>
                <Button variant="ghost" size="sm" onClick={() => void revokeCourseAccess(ca.course_id)}>
                  <Trash2 size={12} />
                </Button>
              </div>
            );
          })}

          {showCoursePanel && (
            <div className="rounded-lg border border-line-soft bg-surface p-3 space-y-1">
              <div className="flex items-center gap-2 pb-1 mb-1 border-b border-line-soft">
                <input
                  type="checkbox"
                  className="rounded"
                  checked={courseSelections.every((s) => s.checked)}
                  onChange={(e) =>
                    setCourseSelections((prev) => prev.map((s) => ({ ...s, checked: e.target.checked })))
                  }
                />
                <span className="text-xs text-ink-muted flex-1">Select all</span>
                <span className="text-xs text-ink-soft w-20 text-center">Role</span>
              </div>
              {courseSelections.map((sel, i) => {
                const course = courseMap[sel.id];
                return (
                  <div key={sel.id} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      className="rounded"
                      checked={sel.checked}
                      onChange={(e) =>
                        setCourseSelections((prev) =>
                          prev.map((s, j) => j === i ? { ...s, checked: e.target.checked } : s)
                        )
                      }
                    />
                    <span className="flex-1 text-sm text-ink">
                      {course ? `${course.name} \u2014 ${course.semester}` : `Course ${sel.id}`}
                    </span>
                    <div className="flex rounded overflow-hidden border border-line-soft text-xs">
                      <button
                        className={`px-2 py-1 ${sel.role === 'HOST' ? 'bg-accent text-on-fill' : 'text-ink-muted hover:text-on-fill'}`}
                        onClick={() => setCourseSelections((prev) => prev.map((s, j) => j === i ? { ...s, role: 'HOST' } : s))}
                      >HOST</button>
                      <button
                        className={`px-2 py-1 ${sel.role === 'PLAYER' ? 'bg-accent text-on-fill' : 'text-ink-muted hover:text-on-fill'}`}
                        onClick={() => setCourseSelections((prev) => prev.map((s, j) => j === i ? { ...s, role: 'PLAYER' } : s))}
                      >PLAYER</button>
                    </div>
                  </div>
                );
              })}
              <div className="flex gap-2 pt-2">
                <Button
                  size="sm"
                  onClick={() => void grantSelectedCourses()}
                  disabled={selectedCourseCount === 0 || grantingCourses}
                >
                  {grantingCourses ? 'Granting\u2026' : `Grant Selected (${selectedCourseCount})`}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setShowCoursePanel(false)}>Cancel</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Game access */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h3 className="font-display text-lg font-extrabold text-ink">Game Access</h3>
            {availableGames.length > 0 && !showGamePanel && (
              <Button size="sm" variant="outline" onClick={() => openGamePanel(availableGames)}>
                Add Games
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {user.game_access.length === 0 && !showGamePanel && (
            <p className="text-ink-soft text-sm">No game access granted.</p>
          )}
          {user.game_access.map((gid) => {
            const game = gameMap[gid];
            return (
              <div key={gid} className="flex items-center justify-between">
                <span className="text-ink text-sm">
                  {game ? game.title : `Game ${gid}`}
                  <span className="text-ink-soft text-xs ml-2">{courseName(game?.course_id ?? null)}</span>
                  {!canUseGame(game) && (
                    <span className="text-warning-ink text-xs ml-2">inactive: not HOST of this course</span>
                  )}
                </span>
                <Button variant="ghost" size="sm" onClick={() => void revokeGameAccess(gid)}>
                  <Trash2 size={12} />
                </Button>
              </div>
            );
          })}

          {showGamePanel && (
            <div className="rounded-lg border border-line-soft bg-surface p-3 space-y-1">
              <div className="flex items-center gap-2 pb-1 mb-1 border-b border-line-soft">
                <input
                  type="checkbox"
                  className="rounded"
                  checked={gameSelections.some((s) => s.checked) && gameSelections.every((s) => s.checked || !canUseGame(gameMap[s.id]))}
                  onChange={(e) =>
                    setGameSelections((prev) =>
                      prev.map((s) => ({ ...s, checked: e.target.checked && canUseGame(gameMap[s.id]) })),
                    )
                  }
                />
                <span className="text-xs text-ink-muted">Select all available</span>
              </div>
              {gameGroups.map(({ courseId, selections }) => {
                const usable = user.role === 'ADMIN' || (courseId !== null && hostedCourseIds.has(courseId));
                return (
                  <div key={courseId ?? 'unassigned'} className="pt-1">
                    <p className="text-xs font-semibold text-ink-muted">
                      {courseName(courseId)}
                      {!usable && (
                        <span className="font-normal text-warning-ink ml-2">
                          {courseId === null
                            ? 'assign these games a course first'
                            : 'grant HOST on this course first'}
                        </span>
                      )}
                    </p>
                    {selections.map(({ sel, index }) => {
                      const game = gameMap[sel.id];
                      return (
                        <label key={sel.id} className={`flex items-center gap-2 pl-3 ${usable ? '' : 'opacity-50'}`}>
                          <input
                            type="checkbox"
                            className="rounded"
                            checked={sel.checked}
                            disabled={!usable}
                            onChange={(e) =>
                              setGameSelections((prev) =>
                                prev.map((s, j) => j === index ? { ...s, checked: e.target.checked } : s)
                              )
                            }
                          />
                          <span className="text-sm text-ink">{game ? game.title : `Game ${sel.id}`}</span>
                        </label>
                      );
                    })}
                  </div>
                );
              })}
              <div className="flex gap-2 pt-2">
                <Button
                  size="sm"
                  onClick={() => void grantSelectedGames()}
                  disabled={selectedGameCount === 0 || grantingGames}
                >
                  {grantingGames ? 'Granting\u2026' : `Grant Selected (${selectedGameCount})`}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setShowGamePanel(false)}>Cancel</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
