import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { Outlet, useNavigate, useParams } from 'react-router-dom';
import { isTokenExpired } from '../../lib/utils';
import { loadImageUrl } from '../../lib/images';
import type { HotspotImage } from '../../components/HotspotCanvas';
import { io, Socket } from 'socket.io-client';
import type {
  AnswerResultPayload,
  PlayerGameOverPayload,
  PlayerJoinedPayload,
  PlayerPhase,
  PlayerResultsPayload,
  QuestionPayload,
  SyncStatePayload,
} from '../../types/game';
import { ThemeToggle } from '../../components/ThemeToggle';
import { Stamp } from '../../components/ui/Stamp';
import { Button } from '../../components/ui/button';

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface GameContextValue {
  phase: PlayerPhase;
  gameStatus: 'LOBBY' | 'IN_PROGRESS';
  roomCode: string;
  playerCount: number;
  hostDisconnected: boolean;
  currentQuestion: QuestionPayload | null;
  questionLocked: boolean;
  lastAnswerData: Record<string, unknown> | null;
  answerResult: AnswerResultPayload | null;
  questionResults: PlayerResultsPayload | null;
  gameOver: PlayerGameOverPayload | null;
  // Hotspot: the current question's image, prefetched when new_question arrives (H11).
  questionImage: (HotspotImage & { questionId: number }) | null;
  emitAnswer: (questionId: number, answerData: Record<string, unknown>, answerTimeMs: number) => void;
}

const GameContext = createContext<GameContextValue | null>(null);

export function useGame(): GameContextValue {
  const ctx = useContext(GameContext);
  if (!ctx) throw new Error('useGame must be used within GameLayout');
  return ctx;
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export default function GameLayout() {
  const { code = '' } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const socketRef = useRef<Socket | null>(null);
  // Ref mirrors phase so socket event closures (registered once) can read current value.
  const phaseRef = useRef<PlayerPhase>('lobby');

  const [phase, setPhase] = useState<PlayerPhase>('lobby');
  const [gameStatus, setGameStatus] = useState<'LOBBY' | 'IN_PROGRESS'>('LOBBY');
  const [playerCount, setPlayerCount] = useState(0);
  const [hostDisconnected, setHostDisconnected] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState<QuestionPayload | null>(null);
  const [questionLocked, setQuestionLocked] = useState(false);
  const [lastAnswerData, setLastAnswerData] = useState<Record<string, unknown> | null>(null);
  const [answerResult, setAnswerResult] = useState<AnswerResultPayload | null>(null);
  const [questionResults, setQuestionResults] = useState<PlayerResultsPayload | null>(null);
  const [gameOver, setGameOver] = useState<PlayerGameOverPayload | null>(null);
  const [questionImage, setQuestionImage] = useState<GameContextValue['questionImage']>(null);
  // Which question's image is loaded/loading, and its object URL (to revoke).
  const imageRef = useRef<{ questionId: number; url: string | null } | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token || isTokenExpired(token)) {
      localStorage.removeItem('token');
      navigate(code ? `/name/${code}` : '/join', { replace: true });
      return;
    }
    if (!code) {
      navigate('/join', { replace: true });
      return;
    }

    const sock = io({
      path: '/socket.io',
      auth: (cb) => cb({ token: localStorage.getItem('token') ?? '' }),
      transports: ['websocket', 'polling'],
    });
    socketRef.current = sock;

    sock.on('connect', () => {
      setError('');
      if (phaseRef.current !== 'gameover') {
        sock.emit('join_room', { room_code: code, role: 'PLAYER' });
      }
    });

    sock.on('connect_error', (err) => {
      if (phaseRef.current !== 'gameover') {
        setError(`Connection error: ${err.message}`);
      }
    });

    sock.on('sync_state', (data: SyncStatePayload) => {
      setPlayerCount(data.playerCount ?? 0);
      if (data.questionLocked) setQuestionLocked(true);
      if (data.status === 'LOBBY') {
        setGameStatus('LOBBY');
        setPhase('lobby');
        navigate(`/game/${code}/lobby`, { replace: true });
      } else if (data.status === 'IN_PROGRESS') {
        // Game already running — update state but don't navigate; new_question
        // (or question_results) will drive routing to the correct page.
        setGameStatus('IN_PROGRESS');
      }
    });

    sock.on('player_joined', (data: PlayerJoinedPayload) => {
      setPlayerCount(data.playerCount);
    });

    sock.on('new_question', (data: QuestionPayload) => {
      // Hotspot image prefetch: start loading before navigating so the fetch overlaps
      // with the player reading the prompt. A re-sent new_question for the same
      // question (reconnect) keeps the image already loaded.
      if (imageRef.current?.questionId !== data.questionId) {
        // T8 D8: warm the browser cache for option images now (C3's immutable header lets
        // the tiles' own fetches read it), so loading overlaps reading the question.
        for (const id of data.config.optionImageIds ?? []) {
          if (typeof id === 'number') loadImageUrl(id).then(URL.revokeObjectURL, () => {});
        }
        releaseImage();
        setQuestionImage(null);
        const imageId = data.config.imageId;
        if (data.type === 'hotspot' && typeof imageId === 'number') {
          const qid = data.questionId;
          imageRef.current = { questionId: qid, url: null };
          setQuestionImage({ questionId: qid, status: 'loading' });
          loadImageUrl(imageId)
            .then((url) => {
              if (imageRef.current?.questionId !== qid) {
                URL.revokeObjectURL(url); // a newer question replaced this one
                return;
              }
              imageRef.current.url = url;
              setQuestionImage({ questionId: qid, status: 'ready', url });
            })
            .catch(() => {
              if (imageRef.current?.questionId === qid) {
                setQuestionImage({ questionId: qid, status: 'error' });
              }
            });
        }
      }
      setCurrentQuestion(data);
      setQuestionLocked(false);
      setLastAnswerData(null);
      setAnswerResult(null);
      setQuestionResults(null);
      setHostDisconnected(false);
      setPhase('question');
      navigate(`/game/${code}/question`);
    });

    sock.on('question_locked', () => {
      setQuestionLocked(true);
    });

    sock.on('question_unlocked', () => {
      setQuestionLocked(false);
    });

    sock.on('answer_received', (data: AnswerResultPayload) => {
      if (data.alreadyAnswered) return; // ignore duplicate-submit echo
      setAnswerResult(data);
      setPhase('feedback');
      navigate(`/game/${code}/feedback`);
    });

    sock.on('question_results', (data: PlayerResultsPayload) => {
      setQuestionResults(data);
      setPhase('results');
      navigate(`/game/${code}/results`);
    });

    sock.on('game_over', (data: PlayerGameOverPayload) => {
      phaseRef.current = 'gameover';
      setGameOver(data);
      setPhase('gameover');
      navigate(`/game/${code}/gameover`);
      sock.disconnect();
    });

    sock.on('host_disconnected', () => {
      setHostDisconnected(true);
    });

    sock.on('game_abandoned', () => {
      navigate('/join', { replace: true });
    });

    sock.on('error', (data: { message: string }) => {
      if (phaseRef.current !== 'gameover') {
        setError(data.message);
      }
    });

    return () => {
      sock.disconnect();
      socketRef.current = null;
    };
  }, [code, navigate]);

  // Release the hotspot image only when the layout unmounts. Not in the socket
  // effect's cleanup: `navigate` changes on every route change, so that effect
  // re-runs on each navigation, and the image must survive question → results.
  useEffect(() => releaseImage, []);

  function releaseImage() {
    if (imageRef.current?.url) URL.revokeObjectURL(imageRef.current.url);
    imageRef.current = null;
  }

  function emitAnswer(questionId: number, answerData: Record<string, unknown>, answerTimeMs: number) {
    setLastAnswerData(answerData);
    socketRef.current?.emit('submit_answer', { question_id: questionId, answer_data: answerData, answer_time_ms: answerTimeMs });
  }

  if (error && phase !== 'gameover') {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center p-4">
        <div className="text-center space-y-5">
          <Stamp tone="danger">Oops</Stamp>
          <p className="text-ink text-lg font-semibold">{error}</p>
          <Button variant="outline" onClick={() => navigate('/join')}>
            Back to Join
          </Button>
        </div>
      </div>
    );
  }

  return (
    <GameContext.Provider
      value={{ phase, gameStatus, roomCode: code, playerCount, hostDisconnected, currentQuestion, questionLocked, lastAnswerData, answerResult, questionResults, gameOver, questionImage, emitAnswer }}
    >
      {/* T9 top bar: room code and the theme switch on every game screen (§5.4). */}
      <header className="sticky top-0 z-40 flex h-12 items-center justify-between border-b-2 border-line bg-surface px-3">
        <span className="font-display text-xl font-extrabold tracking-tight text-ink">
          buzzer<span className="text-accent">.</span>
        </span>
        <span className="font-mono text-sm font-extrabold tracking-[0.15em] text-ink-muted" aria-label={`Room ${code}`}>{code}</span>
        <ThemeToggle compact className="min-h-[44px] -my-1 border-0 shadow-none bg-transparent" />
      </header>
      {hostDisconnected && phase !== 'gameover' && (
        <div className="sticky top-12 inset-x-0 z-30 border-b-2 border-line bg-warning text-on-fill text-center py-2 text-sm font-bold" role="status">
          Host disconnected — waiting for them to reconnect…
        </div>
      )}
      <Outlet />
    </GameContext.Provider>
  );
}
