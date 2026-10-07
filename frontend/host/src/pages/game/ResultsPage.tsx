import { useEffect, useState } from 'react';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import { HotspotView, ringsFromReveal } from '../../components/HotspotView';
import { OrderingView } from '../../components/OrderingView';
import { ImageThumb } from '../../components/ImageThumb';
import { Stamp } from '../../components/ui/Stamp';
import { optionImageId, optionText } from '../../lib/options';
import type { AnswerReveal } from '../../types/game';

const RESULTS_DISPLAY_SECONDS = 10;

// Option inks, matching the player's tiles (static so Tailwind sees them; D10a).
const OPT_BG = ['bg-opt-1', 'bg-opt-2', 'bg-opt-3', 'bg-opt-4', 'bg-opt-5', 'bg-opt-6', 'bg-opt-7', 'bg-opt-8'];
// True / False use the same inks as the phone's True (opt-4) and False (opt-1) tiles.
const TRUE_INK = 3;
const FALSE_INK = 0;

function AnsweredCount({ answered, total }: { answered: number; total: number }) {
  return (
    <p className="font-mono text-base font-bold uppercase tracking-[0.15em] text-ink-soft">
      <span className="text-ink">{answered}</span> / {total} answered
    </p>
  );
}

function optionLabel(i: number): string {
  return String.fromCharCode(65 + i);
}

// ---------------------------------------------------------------------------
// Levenshtein distance — used to colour word-cloud entries for FITB questions
// ---------------------------------------------------------------------------

function levenshtein(a: string, b: string): number {
  const m = a.length, n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, (_, i) =>
    Array.from({ length: n + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0))
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1][j - 1]
          : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[m][n];
}

// ---------------------------------------------------------------------------
// Word Cloud — for fill_in_the_blank questions
// ---------------------------------------------------------------------------

interface WordCloudProps {
  distribution: Record<string, number>;
  answerReveal: AnswerReveal;
  totalAnswered: number;
  totalPlayers: number;
}

function WordCloud({ distribution, answerReveal, totalAnswered, totalPlayers }: WordCloudProps) {
  const entries = Object.entries(distribution).sort(([, a], [, b]) => b - a);
  const maxCount = Math.max(...entries.map(([, c]) => c), 1);

  const isAccuracy =
    'type' in answerReveal && answerReveal.type === 'fill_in_the_blank';
  const acceptedAnswers: string[] =
    isAccuracy && 'acceptedAnswers' in answerReveal
      ? (answerReveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).acceptedAnswers.map(a => a.toLowerCase())
      : [];
  const editDistance: number =
    isAccuracy && 'editDistance' in answerReveal
      ? (answerReveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).editDistance
      : 0;

  function sizeClass(count: number): string {
    const f = count / maxCount;
    if (f > 0.75) return 'text-5xl font-black';
    if (f > 0.5)  return 'text-4xl font-bold';
    if (f > 0.25) return 'text-3xl font-semibold';
    if (f > 0.1)  return 'text-2xl font-medium';
    return 'text-xl';
  }

  function isCorrectWord(word: string): boolean {
    if (!isAccuracy || acceptedAnswers.length === 0) return false;
    return acceptedAnswers.some(a => levenshtein(word.toLowerCase(), a) <= editDistance);
  }

  return (
    <div className="w-full max-w-3xl flex flex-col gap-4">
      {isAccuracy && acceptedAnswers.length > 0 && (
        <p className="text-center text-ink-muted text-xl">
          Correct answer:{' '}
          <span className="text-success-ink font-bold">
            {(answerReveal as { acceptedAnswers: string[] }).acceptedAnswers.join(' / ')}
            {editDistance > 0 && (
              <span className="text-ink-soft font-normal text-sm ml-1">(±{editDistance})</span>
            )}
          </span>
        </p>
      )}

      <div className="flex flex-wrap gap-x-6 gap-y-3 justify-center items-center min-h-32 p-6 bg-surface rounded-3xl border-2 border-line shadow-hard">
        {entries.map(([word, count]) => (
          <span
            key={word}
            title={`${count} player${count !== 1 ? 's' : ''}`}
            className={`${sizeClass(count)} font-display transition-colors ${
              isCorrectWord(word) ? 'text-success-ink underline decoration-success decoration-4 underline-offset-4' : 'text-ink-muted'
            }`}
          >
            {word}
          </span>
        ))}
        {entries.length === 0 && (
          <p className="text-ink-soft text-sm">No answers submitted</p>
        )}
      </div>

      <div className="text-right"><AnsweredCount answered={totalAnswered} total={totalPlayers} /></div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bar Chart — for multiple_choice and true_false
// ---------------------------------------------------------------------------

interface BarChartProps {
  bars: { label: string; count: number; correct: boolean | null; ink: number; imageId?: number | null }[];
  totalAnswered: number;
  totalPlayers: number;
}

function AnswerBarChart({ bars, totalAnswered, totalPlayers }: BarChartProps) {
  const maxCount = Math.max(...bars.map(b => b.count), 1);

  return (
    <div className="w-full max-w-4xl space-y-4">
      {bars.map((bar, i) => {
        const pct = Math.round((bar.count / maxCount) * 100);

        return (
          <div key={i} className="flex items-center gap-4">
            <span className="text-ink font-bold text-xl min-w-[2rem] max-w-[16rem] text-right shrink-0 whitespace-nowrap overflow-hidden text-ellipsis">
              {bar.label}
            </span>
            {typeof bar.imageId === 'number' && (
              <ImageThumb imageId={bar.imageId} alt={bar.label} className="h-12 w-16 shrink-0" />
            )}
            {/* Every option keeps its ink; the answer is marked by a stamp, never by dimming. */}
            <div className="flex-1 h-14 rounded-2xl border-2 border-line bg-sunken overflow-hidden">
              {bar.count > 0 && (
                <div
                  className={`h-full flex items-center justify-end pr-4 border-r-2 border-line transition-all duration-500 halftone ${OPT_BG[bar.ink % 8]}`}
                  style={{ width: `${Math.max(pct, 6)}%` }}
                >
                  <span className="font-mono text-2xl font-extrabold text-on-fill">{bar.count}</span>
                </div>
              )}
            </div>
            <span className="w-40 shrink-0">
              {bar.correct === true ? (
                <Stamp tone="success" className="text-lg">✓ Answer</Stamp>
              ) : bar.count === 0 ? (
                <span className="font-mono text-xl font-bold text-ink-soft">0</span>
              ) : null}
            </span>
          </div>
        );
      })}

      <div className="text-right pt-1"><AnsweredCount answered={totalAnswered} total={totalPlayers} /></div>
    </div>
  );
}

function buildBars(
  reveal: AnswerReveal,
  distribution: Record<string, number>,
  options: string[] | undefined,
  imageIds?: (number | null)[],
): BarChartProps['bars'] {
  if (reveal.type === 'multiple_choice') {
    const opts = options ?? [];
    return opts.map((_, i) => ({
      label: `${optionLabel(i)}  ${optionText(opts, imageIds, i)}`,
      count: distribution[String(i)] ?? 0,
      correct: reveal.correctIndices.includes(i),
      ink: i,
      imageId: optionImageId(imageIds, i),
    }));
  }

  if (reveal.type === 'multi_select') {
    const opts = options ?? [];
    return opts.map((_, i) => ({
      label: `${optionLabel(i)}  ${optionText(opts, imageIds, i)}`,
      count: distribution[String(i)] ?? 0,
      correct: (reveal.answerPoints[i] ?? 0) > 0,
      ink: i,
      imageId: optionImageId(imageIds, i),
    }));
  }

  if (reveal.type === 'true_false') {
    return [
      { label: 'True', count: distribution['true'] ?? 0, correct: reveal.correctValue === true, ink: TRUE_INK },
      { label: 'False', count: distribution['false'] ?? 0, correct: reveal.correctValue === false, ink: FALSE_INK },
    ];
  }

  // completeness (non-FITB) — no right/wrong
  if (options && options.length > 0) {
    return options.map((_, i) => ({
      label: `${optionLabel(i)}  ${optionText(options, imageIds, i)}`,
      count: distribution[String(i)] ?? 0,
      correct: null,
      ink: i,
      imageId: optionImageId(imageIds, i),
    }));
  }

  if ('true' in distribution || 'false' in distribution) {
    return [
      { label: 'True', count: distribution['true'] ?? 0, correct: null, ink: TRUE_INK },
      { label: 'False', count: distribution['false'] ?? 0, correct: null, ink: FALSE_INK },
    ];
  }

  return [];
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ResultsPage() {
  const { questionResults, currentQuestion, autoAdvance, emitAdvance } = useGame();
  const [countdown, setCountdown] = useState(RESULTS_DISPLAY_SECONDS);

  const isLast = currentQuestion
    ? currentQuestion.questionNumber >= currentQuestion.totalQuestions
    : false;

  useEffect(() => {
    if (!autoAdvance) return;
    setCountdown(RESULTS_DISPLAY_SECONDS);
    const interval = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) { clearInterval(interval); emitAdvance(); return 0; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [autoAdvance, questionResults, emitAdvance]);

  const isFitb = currentQuestion?.type === 'fill_in_the_blank';
  const isHotspot = currentQuestion?.type === 'hotspot';
  const isOrdering = currentQuestion?.type === 'ordering';

  const bars =
    !isFitb && questionResults
      ? buildBars(
          questionResults.answerReveal,
          questionResults.answerDistribution,
          currentQuestion?.config?.options,
          currentQuestion?.config?.optionImageIds,
        )
      : [];

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 gap-8">
      <div className="flex flex-col items-center gap-3">
        <p className="rounded-full border-2 border-line bg-ink px-4 py-1 font-mono text-sm font-bold uppercase tracking-[0.2em] text-canvas">
          Q {currentQuestion?.questionNumber} · Results
        </p>
        <h2 className="sr-only">Question {currentQuestion?.questionNumber} Results</h2>
      </div>

      {currentQuestion && (
        <div className="flex items-center justify-center gap-4 max-w-3xl">
          {/* T8 D8: the prompt image, small, beside the prompt. */}
          {typeof currentQuestion.promptImageId === 'number' && (
            <ImageThumb
              imageId={currentQuestion.promptImageId}
              alt={currentQuestion.prompt}
              className="h-20 w-32 shrink-0"
            />
          )}
          <p className="font-display text-4xl font-extrabold tracking-tight text-ink text-center max-w-4xl leading-tight">
            {currentQuestion.prompt}
          </p>
        </div>
      )}

      {questionResults && isHotspot && currentQuestion ? (
        <div className="w-full max-w-4xl">
          {/* Rings under ACCURACY; COMPLETENESS (no target) shows neutral taps only. */}
          <HotspotView
            imageId={currentQuestion.config.imageId}
            aspectRatio={currentQuestion.config.aspectRatio ?? 1}
            label={`Taps for: ${currentQuestion.prompt}`}
            rings={ringsFromReveal(questionResults.answerReveal)}
            taps={questionResults.taps ?? []}
            legend={{
              accuracy: currentQuestion.gradingType === 'ACCURACY',
              distribution: questionResults.answerDistribution,
            }}
            maxHeightVh={50}
          />
          <div className="mt-2 text-center"><AnsweredCount answered={questionResults.totalAnswered} total={questionResults.totalPlayers} /></div>
        </div>
      ) : questionResults && isOrdering && currentQuestion ? (
        <div className="w-full flex flex-col items-center">
          <OrderingView
            items={currentQuestion.config.items ?? []}
            correctOrder={
              questionResults.answerReveal.type === 'ordering'
                ? questionResults.answerReveal.correctOrder
                : undefined
            }
            distribution={questionResults.answerDistribution}
            meanPositions={questionResults.meanPositions}
            accuracy={currentQuestion.gradingType === 'ACCURACY'}
            invalidKey={
              currentQuestion.gradingType === 'ACCURACY' &&
              !(questionResults.answerReveal.type === 'ordering' && questionResults.answerReveal.correctOrder)
            }
          />
          <div className="mt-3 text-center"><AnsweredCount answered={questionResults.totalAnswered} total={questionResults.totalPlayers} /></div>
        </div>
      ) : questionResults && isFitb ? (
        <WordCloud
          distribution={questionResults.answerDistribution}
          answerReveal={questionResults.answerReveal}
          totalAnswered={questionResults.totalAnswered}
          totalPlayers={questionResults.totalPlayers}
        />
      ) : questionResults ? (
        <AnswerBarChart
          bars={bars}
          totalAnswered={questionResults.totalAnswered}
          totalPlayers={questionResults.totalPlayers}
        />
      ) : null}

      <div className="flex flex-col items-center gap-2">
        <Button size="lg" onClick={emitAdvance} className="px-10">
          {isLast ? 'Show Final Results' : 'Next Question'}
        </Button>
        {autoAdvance && (
          <p className="font-mono text-sm font-bold uppercase tracking-[0.15em] text-ink-soft tabular-nums">
            Auto-advancing in {countdown}s
          </p>
        )}
      </div>
    </div>
  );
}
