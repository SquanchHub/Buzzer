import { useEffect } from 'react';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import { TimerBar } from '../../components/ui/TimerBar';
import { HotspotView } from '../../components/HotspotView';
import { OrderingItems } from '../../components/OrderingView';
import { ImageThumb } from '../../components/ImageThumb';

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
        <p className="text-slate-400">Loading question…</p>
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
      <div className="flex items-center gap-3 text-sm uppercase tracking-wider">
        <span className="text-slate-400">
          Question {currentQuestion.questionNumber} of {currentQuestion.totalQuestions}
        </span>
        <span className="text-slate-600">·</span>
        <span className="text-slate-400">{typeLabel[currentQuestion.type] ?? currentQuestion.type}</span>
        <span className="text-slate-600">·</span>
        <span className={currentQuestion.gradingType === 'COMPLETENESS' ? 'text-amber-400' : 'text-indigo-400'}>
          {currentQuestion.gradingType === 'COMPLETENESS' ? 'Participation' : 'Accuracy'}
        </span>
        {currentQuestion.type === 'fill_in_the_blank' && currentQuestion.gradingType === 'ACCURACY' && (
          <>
            <span className="text-slate-600">·</span>
            <span className="text-slate-400 normal-case">
              {editDistanceLabel(currentQuestion.editDistance ?? 0)}
            </span>
          </>
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
        <h2 className="text-4xl font-bold text-slate-100 text-center max-w-3xl leading-tight">
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
              <div key={i} className="flex flex-col gap-2 rounded-xl border border-slate-700 bg-slate-800/60 p-3">
                {typeof id === 'number' ? (
                  <ImageThumb imageId={id} alt={`Option ${optionLabel(i)}`} className="h-36 w-full" />
                ) : (
                  <span className="flex h-36 items-center justify-center text-center text-lg text-slate-200">{text}</span>
                )}
                <span className="text-lg font-bold text-slate-100">
                  {optionLabel(i)}
                  {typeof id === 'number' && text.trim() && <span className="ml-2 font-medium text-slate-300">{text}</span>}
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

      <div className="text-slate-300 text-xl">
        {answeredCount} / {playerCount} answered
        {allAnswered && <span className="ml-3 text-green-400 font-semibold">All answered!</span>}
        {questionLocked && <span className="ml-3 text-amber-400 font-semibold">· Answers locked</span>}
      </div>

      <div className="flex gap-4">
        <Button
          size="lg"
          variant="outline"
          onClick={emitLockQuestion}
          className={`px-10 ${questionLocked ? 'border-amber-500 text-amber-400 hover:bg-amber-500/10' : ''}`}
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
