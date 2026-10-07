import { BrowserRouter, Navigate, Outlet, Route, Routes, useNavigate, NavLink } from 'react-router-dom';
import { tokenRole } from './lib/utils';
import { BookOpen, Users, Gamepad2, UserX, LogOut, History, MonitorPlay, Smartphone } from 'lucide-react';
import { ThemeToggle } from './components/ThemeToggle';
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

  // T9: the sidebar is an ink slab in both themes (docs/plans/t9-theming.md §7.4); `slab`
  // switches the focus outline to a colour that contrasts with it.
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-semibold transition-colors ${
      isActive
        ? 'bg-accent text-on-fill'
        : 'text-canvas hover:bg-canvas/10'
    }`;

  const secondaryLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
      isActive
        ? 'bg-accent text-on-fill'
        : 'text-canvas/70 hover:bg-canvas/10 hover:text-canvas'
    }`;

  return (
    <div className="flex min-h-screen">
      <aside className="slab sticky top-0 h-screen w-56 shrink-0 bg-ink text-canvas flex flex-col">
        <div className="px-5 py-5">
          <p className="font-display text-2xl font-extrabold leading-none tracking-tight">
            buzzer<span className="text-accent">.</span>
          </p>
          <p className="mt-1 font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-canvas/70">Admin desk</p>
        </div>
        <nav className="flex-1 px-3 space-y-6">
          <div className="space-y-0.5">
            <p className="px-3 pb-1 font-mono text-[10px] font-bold uppercase tracking-[0.25em] text-canvas/70">
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
          <div className="space-y-0.5">
            <p className="px-3 pb-1 font-mono text-[10px] font-bold uppercase tracking-[0.25em] text-canvas/70">
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
        <div className="p-3 border-t border-canvas/20 space-y-1">
          <ThemeToggle onSlab className="mb-2 w-full justify-between" />
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
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-semibold text-canvas hover:bg-canvas/10 w-full transition-colors"
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
