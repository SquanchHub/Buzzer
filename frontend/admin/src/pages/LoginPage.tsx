import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { tokenRole } from '../lib/utils';
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
  const notice = (useLocation().state as { message?: string } | null)?.message;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/login', { username, password });
      if (tokenRole(data.access_token) !== 'ADMIN') {
        // Don't store it: that would also replace the host/player apps' session.
        setError('This account is not an admin. Use the Host app to host games.');
        return;
      }
      localStorage.setItem('token', data.access_token);
      navigate('/users');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center p-4">
      <ThemeToggle className="absolute right-4 top-4" />
      <Card className="w-full max-w-sm">
        <CardHeader>
          <p className="font-mono text-[11px] font-bold uppercase tracking-[0.3em] text-accent-ink">Buzzer · Admin desk</p>
          <h1 className="mt-2 font-display text-3xl font-extrabold tracking-tight text-ink">Sign in</h1>
          <p className="text-ink-muted text-sm mt-1">Courses, people, games and sessions.</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
            {notice && !error && <p className="text-warning-ink text-sm">{notice}</p>}
            {error && <p className="text-danger-ink text-sm">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Signing in\u2026' : 'Sign In'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
