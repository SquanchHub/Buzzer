import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { ThemeToggle } from '../components/ThemeToggle';
import { Card, CardContent, CardHeader } from '../components/ui/card';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Handle return from OAuth2 — exchange temp token for full access token
  useEffect(() => {
    if (searchParams.get('from') !== 'oauth2') return;

    const oauthError = searchParams.get('error');
    if (oauthError) {
      setError(oauthError);
      return;
    }

    const match = window.location.hash.match(/oauth2_data=([^&]+)/);
    if (!match) return;

    let tempToken: string;
    try {
      const data = JSON.parse(decodeURIComponent(match[1]));
      tempToken = data.temp_token;
      if (!tempToken) throw new Error();
    } catch {
      setError('Invalid authentication response');
      return;
    }

    setLoading(true);
    fetch('/api/auth/exchange-temp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tempToken}` },
    })
      .then(res => res.ok ? res.json() : res.json().then((e: { detail?: string }) => Promise.reject(e.detail ?? 'Sign-in failed')))
      .then((data: { access_token: string }) => {
        localStorage.setItem('token', data.access_token);
        window.history.replaceState(null, '', window.location.pathname);
        navigate('/home');
      })
      .catch((msg: unknown) => {
        setError(typeof msg === 'string' ? msg : 'Sign-in failed');
        setLoading(false);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/login', { username, password });
      localStorage.setItem('token', data.access_token);
      navigate('/home');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center p-4">
      <ThemeToggle className="absolute right-4 top-4" />
      <Card className="w-full max-w-md">
        <CardHeader>
          <p className="font-display text-5xl font-extrabold leading-none tracking-tight text-ink [text-shadow:3px_3px_0_rgb(var(--accent))]">
            buzzer
          </p>
          <p className="mt-3 font-mono text-[11px] font-bold uppercase tracking-[0.3em] text-ink-soft">Host sign in</p>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Primary: UW NetID SSO */}
          <a
            href="/api/auth/oauth2-callback?redirect_to=/host/login"
            className={`flex items-center justify-center w-full py-2.5 px-4 rounded-xl border-2 border-line font-bold transition-[transform,box-shadow] duration-75
              ${loading
                ? 'bg-sunken text-ink-soft pointer-events-none'
                : 'bg-accent text-on-fill shadow-hard active:translate-x-1 active:translate-y-1 active:shadow-none'
              }`}
          >
            Sign in with UW NetID
          </a>

          <div className="flex items-center gap-3">
            <div className="flex-1 border-t-2 border-dashed border-line-soft" />
            <span className="font-mono text-[11px] uppercase tracking-widest text-ink-soft">or local account</span>
            <div className="flex-1 border-t-2 border-dashed border-line-soft" />
          </div>

          {/* Secondary: username/password for admin & local accounts */}
          <form onSubmit={handleSubmit} className="space-y-3">
            <Input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="Username"
              autoComplete="username"
              required
            />
            <Input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              required
            />
            {error && <p className="text-danger-ink text-sm">{error}</p>}
            <Button type="submit" variant="outline" className="w-full" disabled={loading}>
              {loading ? 'Signing in…' : 'Sign In'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
