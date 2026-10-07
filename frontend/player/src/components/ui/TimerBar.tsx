import { useEffect, useRef, useState } from 'react';

interface TimerBarProps {
  totalSeconds: number;
  paused?: boolean;
}

export function TimerBar({ totalSeconds, paused = false }: TimerBarProps) {
  const [timeLeft, setTimeLeft] = useState(totalSeconds);
  const pausedRef = useRef(paused);
  const endTimeRef = useRef(Date.now() + totalSeconds * 1000);
  const frozenRef = useRef(totalSeconds);

  // Keep pausedRef in sync; on resume, reset endTime from the frozen value
  useEffect(() => {
    pausedRef.current = paused;
    if (!paused) {
      endTimeRef.current = Date.now() + frozenRef.current * 1000;
    }
  }, [paused]);

  useEffect(() => {
    if (totalSeconds <= 0) return;

    const id = setInterval(() => {
      if (pausedRef.current) {
        // Slide endTime forward so resume continues from the frozen value
        endTimeRef.current = Date.now() + frozenRef.current * 1000;
        return;
      }
      const remaining = Math.max(0, (endTimeRef.current - Date.now()) / 1000);
      frozenRef.current = remaining;
      setTimeLeft(remaining);
    }, 100);

    return () => clearInterval(id);
  }, []); // runs once on mount; parent uses key={questionId} to remount per question

  const fraction = Math.max(0, Math.min(1, timeLeft / totalSeconds));
  const displaySeconds = Math.ceil(timeLeft);

  // success → warning at 30% → danger at 10% (docs/plans/t9-theming.md §7.1)
  const barColor =
    fraction > 0.3 ? 'bg-success' :
    fraction > 0.1 ? 'bg-warning' :
    'bg-danger';

  return (
    <div className="w-full flex items-center gap-4">
      <div className="flex-1 h-4 rounded-full border-2 border-line bg-sunken overflow-hidden">
        <div
          className={`h-full border-r-2 border-line transition-[width] duration-100 ease-linear ${barColor}`}
          style={{ width: `${fraction * 100}%` }}
        />
      </div>
      <span className="text-ink font-mono text-lg w-12 font-extrabold text-right tabular-nums shrink-0">
        {displaySeconds}<span className="text-ink-soft text-[0.6em]">s</span>
      </span>
    </div>
  );
}
