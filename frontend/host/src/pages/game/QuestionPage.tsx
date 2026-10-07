import { useEffect } from 'react';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import { TimerBar } from '../../components/ui/TimerBar';
import { HotspotView } from '../../components/HotspotView';
import { OrderingItems } from '../../components/OrderingView';
import { ImageThumb } from '../../components/ImageThumb';
import { Stamp } from '../../components/ui/Stamp';

// Static maps so Tailwind sees every class (docs/plans/t9-theming.md D10a).
const OPT_BORDER = ['border-opt-1', 'border-opt-2', 'border-opt-3', 'border-opt-4', 'border-opt-5', 'border-opt-6', 'border-opt-7', 'border-opt-8'];
const OPT_BG = ['bg-opt-1', 'bg-opt-2', 'bg-opt-3', 'bg-opt-4', 'bg-opt-5', 'bg-opt-6', 'bg-opt-7', 'bg-opt-8'];
const CHIP = 'rounded-full border-2 border-line px-3 py-1';

const optionLabel = (i: number) => String.fromCharCode(65 + i); // A, B, C, …

export default function QuestionPage() {
  const { currentQuestion, answeredCount, playerCount, allAnswered, answerPhaseEnded, questionLocked, lockedTimerSeconds, autoAdvance, emitAdvance, emitLockQuestion } = useGame();

  useEffect(() => {
    if (!autoAdvance || !answerPhaseEnded) return;
    const id = setTimeout(emitAdvance, 1500);
    return () => clearTimeout(id);
  }, [autoAdvance, answerPhaseEnded, emitAdvance]);

  if (!currentQuestion) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="font-mono text-lg font-bold uppercase tracking-[0.2em] text-ink-muted">Loading question…</p>
      </div>
    );
  }

  const typeLabel: Record<string, string> = {
    multiple_choice: 'Multiple Choice',
    true_false: 'True / False',
    fill_in_the_blank: 'Fill in the Blank',
    multi_select: 'Multi-Select',
    hotspot: 'Hotspot',
    ordering: 'Ordering',
  };

  function editDistanceLabel(d: number): string {
    if (d === 0) return 'Exact spelling required';
    if (d === 1) return 'Up to 1 typo allowed';
    return `Up to ${d} typos allowed`;
  }

  const optionImageIds = currentQuestion.config.optionImageIds ?? [];

  const remainingSeconds = questionLocked && lockedTimerSeconds !== null
    ? lockedTimerSeconds
    : currentQuestion.startedAt
      ? Math.max(0, currentQuestion.timeLimitSeconds - (Date.now() - new Date(currentQuestion.startedAt).getTime()) / 1000)
      : currentQuestion.timeLimitSeconds;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 gap-8">
      <div className="flex flex-wrap items-center justify-center gap-2 font-mono text-sm font-bold uppercase tracking-[0.15em]">
        <span className={`${CHIP} bg-ink text-canvas`}>
          Q {currentQuestion.questionNumber} / {currentQuestion.totalQuestions}
        </span>
        <span className={`${CHIP} bg-surface text-ink`}>{typeLabel[currentQuestion.type] ?? currentQuestion.type}</span>
        <span className={`${CHIP} ${currentQuestion.gradingType === 'COMPLETENESS' ? 'bg-warning/20 text-warning-ink' : 'bg-accent/15 text-accent-ink'}`}>
          {currentQuestion.gradingType === 'COMPLETENESS' ? 'Participation' : 'Accuracy'}
        </span>
        {currentQuestion.type === 'fill_in_the_blank' && currentQuestion.gradingType === 'ACCURACY' && (
          <span className={`${CHIP} bg-surface text-ink-muted normal-case tracking-normal`}>
            {editDistanceLabel(currentQuestion.editDistance ?? 0)}
          </span>
        )}
      </div>

      <div className="w-full max-w-3xl">
        <TimerBar
          key={currentQuestion.questionId}
          totalSeconds={currentQuestion.timeLimitSeconds}
          initialSeconds={remainingSeconds}
          paused={questionLocked}
        />
      </div>

      {/* T8 D8: the prompt image, large, above the prompt text. */}
      {!questionLocked && typeof currentQuestion.promptImageId === 'number' && (
        <ImageThumb
          imageId={currentQuestion.promptImageId}
          alt={currentQuestion.prompt}
          className="h-[38vh] w-full max-w-3xl"
        />
      )}

      {!questionLocked && (
        <h2 className="font-display text-5xl md:text-6xl font-extrabold tracking-tight text-ink text-center max-w-5xl leading-[1.05]">
          {currentQuestion.prompt}
        </h2>
      )}

      {/* T8 D8: option tiles, only for questions with option images (text-only choices stay
          on the phones, as before). */}
      {!questionLocked && optionImageIds.some((id) => typeof id === 'number') && (
        <div className="grid w-full max-w-4xl grid-cols-2 gap-4 md:grid-cols-4">
          {(currentQuestion.config.options ?? []).map((text, i) => {
            const id = optionImageIds[i];
            return (
              <div key={i} className={`flex flex-col gap-2 rounded-2xl border-4 ${OPT_BORDER[i % 8]} bg-surface p-3 shadow-hard`}>
                {typeof id === 'number' ? (
                  <ImageThumb imageId={id} alt={`Option ${optionLabel(i)}`} className="h-36 w-full" />
                ) : (
                  <span className="flex h-36 items-center justify-center text-center text-lg text-ink">{text}</span>
                )}
                <span className="flex items-center text-lg font-bold text-ink">
                  <span className={`inline-flex h-8 w-8 items-center justify-center rounded-full border-2 border-line ${OPT_BG[i % 8]} font-mono text-on-fill`}>
                    {optionLabel(i)}
                  </span>
                  {typeof id === 'number' && text.trim() && <span className="ml-2 font-medium text-ink-muted">{text}</span>}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Hotspot: the image only — no rings, no taps while the question is open (H5). */}
      {!questionLocked && currentQuestion.type === 'hotspot' && (
        <div className="w-full max-w-4xl">
          <HotspotView
            imageId={currentQuestion.config.imageId}
            aspectRatio={currentQuestion.config.aspectRatio ?? 1}
            label={currentQuestion.prompt}
            maxHeightVh={50}
          />
        </div>
      )}

      {/* Ordering: the items in display order — no statistics while open (O11). */}
      {!questionLocked && currentQuestion.type === 'ordering' && (
        <OrderingItems items={currentQuestion.config.items ?? []} />
      )}

      <div className="flex flex-wrap items-center justify-center gap-6">
        <p className="text-ink-muted text-xl font-semibold">
          <span className="font-mono text-4xl font-extrabold text-ink">{answeredCount}</span>
          <span className="font-mono text-2xl font-bold text-ink-soft"> / {playerCount}</span> answered
        </p>
        {allAnswered && <Stamp tone="success" className="text-xl">All in!</Stamp>}
        {questionLocked && <Stamp tone="warning" className="text-xl">Locked</Stamp>}
      </div>

      <div className="flex gap-4">
        <Button
          size="lg"
          variant="outline"
          onClick={emitLockQuestion}
          className={`px-10 ${questionLocked ? 'bg-warning text-on-fill hover:bg-warning' : ''}`}
        >
          {questionLocked ? 'Unlock Question' : 'Lock Question'}
        </Button>
        <Button size="lg" onClick={emitAdvance} className="px-10">
          Show Results
        </Button>
      </div>
    </div>
  );
}
