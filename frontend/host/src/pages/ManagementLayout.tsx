import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { cn } from '../lib/utils';

/** Shared top bar for the host's non-game pages (docs/plans/t4-ui-restructuring.md §6.3). */
export default function ManagementLayout() {
  const navigate = useNavigate();

  function signOut() {
    localStorage.removeItem('token');
    navigate('/login');
  }

  const link = ({ isActive }: { isActive: boolean }) =>
    cn(
      'px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
      isActive ? 'bg-slate-700 text-slate-100' : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800',
    );

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-slate-800 bg-slate-900/80">
        <nav className="mx-auto flex max-w-4xl items-center gap-1 px-4 py-3">
          <span className="mr-4 font-bold text-slate-100">Buzzer Host</span>
          <NavLink to="/home" className={link}>Home</NavLink>
          <NavLink to="/sessions" className={link}>Sessions</NavLink>
          <button
            type="button"
            onClick={signOut}
            className="ml-auto px-3 py-1.5 rounded-md text-sm text-slate-400 hover:text-slate-100 hover:bg-slate-800"
          >
            Sign out
          </button>
        </nav>
      </header>
      <main className="flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
