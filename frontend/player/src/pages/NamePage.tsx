import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { isTokenExpired } from '../lib/utils';
import { PageShell } from '../components/PageShell';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardHeader } from '../components/ui/card';

type Mode = 'guest' | 'netid' | 'local';

export default function NamePage() {
  const { code = '' } = useParams<{ code: string }>();
  const navigate = useNavigate();

  // Only treat the token as valid if it is present AND not expired
  const isAuthenticated = !isTokenExpired(localStorage.getItem('token'));
  const [mode, setMode] = useState<Mode>(isAuthenticated ? 'netid' : 'guest');

  // Guest fields — pre-fill from localStorage if available
  const [displayName, setDisplayName] = useState(() => localStorage.getItem('playerName') ?? '');
  const [email, setEmail] = useState(() => localStorage.getItem('playerEmail') ?? '');

  // Login fields
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleGuest(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/guest', {
        display_name: displayName.trim(),
        email: email.trim().toLowerCase(),
        room_code: code,
      });
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('playerName', displayName.trim());
      localStorage.setItem('playerEmail', email.trim().toLowerCase());
      navigate(`/game/${code}/lobby`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to join');
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/login', { username, password });
      localStorage.setItem('token', data.access_token);
      navigate(`/game/${code}/lobby`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageShell>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <p className="text-center font-mono text-[11px] font-bold uppercase tracking-[0.3em] text-ink-soft">Joining room</p>
          <h1 className="text-center font-mono text-4xl font-extrabold tracking-[0.12em] text-ink">{code}</h1>

          {/* Mode toggle — hidden when already authenticated */}
          {!isAuthenticated && (
            <div className="flex mt-4 rounded-xl border-2 border-line bg-surface p-1 gap-1">
              <button
                type="button"
                onClick={() => { setMode('guest'); setError(''); }}
                className={`flex-1 min-h-[44px] rounded-lg text-sm font-bold transition-colors ${
                  mode === 'guest'
                    ? 'bg-ink text-canvas'
                    : 'text-ink-muted hover:text-ink'
                }`}
              >
                Join as Guest
              </button>
              <button
                type="button"
                onClick={() => { setMode('netid'); setError(''); }}
                className={`flex-1 min-h-[44px] rounded-lg text-sm font-bold transition-colors ${
                  mode === 'netid' || mode === 'local'
                    ? 'bg-ink text-canvas'
                    : 'text-ink-muted hover:text-ink'
                }`}
              >
                Sign In
              </button>
            </div>
          )}
        </CardHeader>

        <CardContent>
          {mode === 'guest' && (
            <form onSubmit={handleGuest} className="space-y-4">
              <div>
                <label className="block font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-ink-muted mb-1.5">Display Name</label>
                <Input
                  type="text"
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  placeholder="Your name"
                  maxLength={50}
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="block font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-ink-muted mb-1.5">Email</label>
                <Input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                />
              </div>
              {error && <p className="text-danger-ink text-sm text-center">{error}</p>}
              <Button
                type="submit"
                className="w-full"
                size="lg"
                disabled={loading || !displayName.trim() || !email.trim()}
              >
                {loading ? 'Joining…' : 'Join Game'}
              </Button>
            </form>
          )}

          {mode === 'netid' && (
            <div className="space-y-3">
              {isAuthenticated ? (
                /* Already signed in via OAuth2 — go straight to lobby */
                <Button
                  className="w-full"
                  size="lg"
                  onClick={() => navigate(`/game/${code}/lobby`)}
                >
                  Join Game
                </Button>
              ) : (
                /* Trigger OAuth2 — save room code so we can return here after auth */
                <a
                  href="/api/auth/oauth2-callback?redirect_to=/player/login"
                  onClick={() => sessionStorage.setItem('joinRoomCode', code)}
                  className="flex items-center justify-center w-full py-4 px-4 rounded-xl border-2 border-line font-bold text-lg bg-accent text-on-fill shadow-hard transition-[transform,box-shadow] duration-75 active:translate-x-1 active:translate-y-1 active:shadow-none"
                >
                  Sign in with UW NetID
                </a>
              )}
              {error && <p className="text-danger-ink text-sm text-center">{error}</p>}
              {!isAuthenticated && (
                <button
                  type="button"
                  onClick={() => { setMode('local'); setError(''); }}
                  className="w-full text-ink-soft text-sm hover:text-ink-muted transition-colors"
                >
                  Use local account instead
                </button>
              )}
            </div>
          )}

          {mode === 'local' && (
            <form onSubmit={handleLogin} className="space-y-4">
              <Input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Username"
                autoComplete="username"
                required
                autoFocus
              />
              <Input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Password"
                autoComplete="current-password"
                required
              />
              {error && <p className="text-danger-ink text-sm text-center">{error}</p>}
              <Button
                type="submit"
                className="w-full"
                size="lg"
                disabled={loading || !username || !password}
              >
                {loading ? 'Signing in…' : 'Sign In & Join'}
              </Button>
              <button
                type="button"
                onClick={() => { setMode('netid'); setError(''); }}
                className="w-full text-ink-soft text-sm hover:text-ink-muted transition-colors"
              >
                ← Back to NetID sign in
              </button>
            </form>
          )}

          <button
            type="button"
            onClick={() => navigate('/join')}
            className="w-full mt-3 text-ink-soft text-sm hover:text-ink-muted transition-colors"
          >
            ← Different room code
          </button>
        </CardContent>
      </Card>
    </PageShell>
  );
}
