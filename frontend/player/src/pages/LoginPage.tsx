import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { PageShell } from '../components/PageShell';
import { Stamp } from '../components/ui/Stamp';
import { Button } from '../components/ui/button';

/**
 * Landing page for OAuth2 returns (/player/login?from=oauth2#oauth2_data=...).
 * Exchanges the temp token for a full access token, then sends the player
 * back to the room they were trying to join (stored in sessionStorage).
 */
export default function LoginPage() {
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    if (searchParams.get('from') !== 'oauth2') {
      navigate('/join', { replace: true });
      return;
    }

    const oauthError = searchParams.get('error');
    if (oauthError) {
      setError(oauthError);
      return;
    }

    const match = window.location.hash.match(/oauth2_data=([^&]+)/);
    if (!match) {
      setError('Invalid authentication response');
      return;
    }

    let tempToken: string;
    try {
      const data = JSON.parse(decodeURIComponent(match[1]));
      tempToken = data.temp_token;
      if (!tempToken) throw new Error();
    } catch {
      setError('Invalid authentication response');
      return;
    }

    fetch('/api/auth/exchange-temp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tempToken}` },
    })
      .then(res => res.ok ? res.json() : res.json().then((e: { detail?: string }) => Promise.reject(e.detail ?? 'Sign-in failed')))
      .then((data: { access_token: string }) => {
        localStorage.setItem('token', data.access_token);
        window.history.replaceState(null, '', window.location.pathname);
        const roomCode = sessionStorage.getItem('joinRoomCode');
        sessionStorage.removeItem('joinRoomCode');
        navigate(roomCode ? `/name/${roomCode}` : '/join', { replace: true });
      })
      .catch((msg: unknown) => {
        setError(typeof msg === 'string' ? msg : 'Sign-in failed. Please try again.');
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <PageShell>
        <div className="text-center space-y-5">
          <Stamp tone="danger">Sign-in failed</Stamp>
          <p className="text-ink font-semibold">{error}</p>
          <Button variant="outline" onClick={() => navigate('/join')}>
            ← Back to join
          </Button>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <p className="font-mono text-sm font-bold uppercase tracking-[0.3em] text-ink-muted animate-pulse">Signing in…</p>
    </PageShell>
  );
}
