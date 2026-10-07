import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { cn } from '../lib/utils';
import { ThemeToggle } from '../components/ThemeToggle';

/** Shared top bar for the host's non-game pages (docs/plans/t4-ui-restructuring.md §6.3). */
export default function ManagementLayout() {
  const navigate = useNavigate();

  function signOut() {
    localStorage.removeItem('token');
    navigate('/login');
  }

  const link = ({ isActive }: { isActive: boolean }) =>
    cn(
      'px-3 py-1.5 rounded-full text-sm font-bold transition-colors',
      isActive ? 'bg-ink text-canvas' : 'text-ink-muted hover:text-ink hover:bg-sunken',
    );

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-20 border-b-2 border-line bg-surface">
        <nav className="mx-auto flex max-w-5xl items-center gap-1 px-4 py-2.5">
          <span className="mr-5 font-display text-2xl font-extrabold leading-none tracking-tight text-ink">
            buzzer<span className="text-accent">.</span>
            <span className="ml-2 align-middle font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-ink-soft">host</span>
          </span>
          <NavLink to="/home" className={link}>Home</NavLink>
          <NavLink to="/sessions" className={link}>Sessions</NavLink>
          <button
            type="button"
            onClick={signOut}
            className="ml-auto px-3 py-1.5 rounded-full text-sm font-bold text-ink-muted hover:text-ink hover:bg-sunken"
          >
            Sign out
          </button>
          <ThemeToggle className="ml-2" />
        </nav>
      </header>
      <main className="flex-1 px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
