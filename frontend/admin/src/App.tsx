import { BrowserRouter, Navigate, Outlet, Route, Routes, useNavigate, NavLink } from 'react-router-dom';
import { tokenRole } from './lib/utils';
import { BookOpen, Users, Gamepad2, UserX, LogOut, History, MonitorPlay, Smartphone } from 'lucide-react';
import LoginPage from './pages/LoginPage';
import CoursesPage from './pages/CoursesPage';
import CourseDetailPage from './pages/CourseDetailPage';
import RosterPage from './pages/RosterPage';
import ImagesPage from './pages/ImagesPage';
import UsersPage from './pages/UsersPage';
import UserDetailPage from './pages/UserDetailPage';
import GuestsPage from './pages/GuestsPage';
import GamesPage from './pages/GamesPage';
import QuestionEditorPage from './pages/QuestionEditorPage';
import SessionsPage from './pages/SessionsPage';

function RequireAdmin() {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  // UX only: the server enforces require_admin on every request. The token is
  // shared with the host and player apps (same origin), so it is left in place.
  if (tokenRole(token) !== 'ADMIN') {
    return (
      <Navigate
        to="/login"
        replace
        state={{ message: 'Your session has expired or this account is not an admin. Sign in with an admin account.' }}
      />
    );
  }
  return <Outlet />;
}

function AdminLayout() {
  const navigate = useNavigate();

  function logout() {
    localStorage.removeItem('token');
    navigate('/login');
  }

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors ${
      isActive
        ? 'bg-indigo-600 text-white'
        : 'text-slate-300 hover:bg-slate-700 hover:text-slate-100'
    }`;

  const secondaryLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-4 py-2 rounded-lg text-xs font-medium transition-colors ${
      isActive
        ? 'bg-slate-700 text-slate-100'
        : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
    }`;

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 bg-slate-900 border-r border-slate-700 flex flex-col">
        <div className="px-6 py-5 border-b border-slate-700">
          <h1 className="text-lg font-bold text-white">Buzzer Admin</h1>
        </div>
        <nav className="flex-1 p-3 space-y-6">
          <div className="space-y-1">
            <p className="px-4 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Administration
            </p>
            <NavLink to="/users" className={linkClass}>
              <Users size={16} /> Users
            </NavLink>
            <NavLink to="/courses" className={linkClass}>
              <BookOpen size={16} /> Courses
            </NavLink>
            <NavLink to="/guests" className={linkClass}>
              <UserX size={16} /> Guests
            </NavLink>
          </div>
          {/* Host-side content tools, kept for admins but visually secondary. */}
          <div className="space-y-1">
            <p className="px-4 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Content &amp; hosting
            </p>
            <NavLink to="/games" className={secondaryLinkClass}>
              <Gamepad2 size={14} /> Games
            </NavLink>
            <NavLink to="/sessions" className={secondaryLinkClass}>
              <History size={14} /> Sessions
            </NavLink>
          </div>
        </nav>
        <div className="p-3 border-t border-slate-700 space-y-1">
          {/* Same origin under nginx, so the admin arrives signed in. The host link targets
              /host/home: the host app's root redirects to its login form even with a token.
              In `npm run dev` each app has its own port and these paths don't resolve. */}
          <a href="/host/home" className={secondaryLinkClass({ isActive: false })}>
            <MonitorPlay size={14} /> Open Host app
          </a>
          <a href="/player/" className={secondaryLinkClass({ isActive: false })}>
            <Smartphone size={14} /> Open Player app
          </a>
          <button
            onClick={logout}
            className="flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium text-slate-300 hover:bg-slate-700 hover:text-slate-100 w-full transition-colors"
          >
            <LogOut size={16} /> Logout
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAdmin />}>
          <Route element={<AdminLayout />}>
            <Route path="/courses" element={<CoursesPage />} />
            <Route path="/courses/:courseId" element={<CourseDetailPage />} />
            <Route path="/courses/:courseId/roster" element={<RosterPage />} />
            <Route path="/courses/:courseId/images" element={<ImagesPage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/users/:userId" element={<UserDetailPage />} />
            <Route path="/guests" element={<GuestsPage />} />
            <Route path="/games" element={<GamesPage />} />
            <Route path="/games/:gameId/questions" element={<QuestionEditorPage />} />
            <Route path="/sessions" element={<SessionsPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/users" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
