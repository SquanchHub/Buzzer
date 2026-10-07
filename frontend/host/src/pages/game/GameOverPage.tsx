import { useNavigate } from 'react-router-dom';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import { HotspotView, ringsFromReveal } from '../../components/HotspotView';
import { OrderingView } from '../../components/OrderingView';
import { ImageThumb } from '../../components/ImageThumb';
import { Card } from '../../components/ui/card';
import { Stamp } from '../../components/ui/Stamp';
import { optionImageId, optionText } from '../../lib/options';
import type { AnswerReveal, HostQuestionSummaryItem } from '../../types/game';

const TARGET_BUCKETS = 8;

// Option inks, matching the phones' tiles (static so Tailwind sees them; D10a).
const OPT_BG = ['bg-opt-1', 'bg-opt-2', 'bg-opt-3', 'bg-opt-4', 'bg-opt-5', 'bg-opt-6', 'bg-opt-7', 'bg-opt-8'];

interface Bucket {
  label: string;
  count: number;
  rangeStart: number;
  rangeEnd: number;
}

function chooseWidth(ceiling: number): number {
  const N = ceiling + 1;
  let bestW = 1;
  let bestDiff = Infinity;
  for (let w = 1; w * w <= N; w++) {
    if (N % w !== 0) continue;
    for (const cand of [w, N / w]) {
      const numBins = N / cand;
      if (numBins < 2) continue;
      const diff = Math.abs(numBins - TARGET_BUCKETS);
      if (diff < bestDiff) { bestDiff = diff; bestW = cand; }
    }
  }
  if (bestDiff > TARGET_BUCKETS) bestW = Math.max(1, Math.ceil(N / TARGET_BUCKETS));
  return bestW;
}

function buildBuckets(scores: number[], maxPossibleScore: number): Bucket[] {
  const ceiling = Math.max(maxPossibleScore, 1);
  const width = chooseWidth(ceiling);
  const numBuckets = Math.ceil((ceiling + 1) / width);
  const buckets: Bucket[] = Array.from({ length: numBuckets }, (_, i) => {
    const start = i * width;
    const end = Math.min(start + width - 1, ceiling);
    const label = start === end ? `${start}` : `${start}–${end}`;
    return { label, count: 0, rangeStart: start, rangeEnd: end };
  });
  for (const score of scores) {
    const idx = Math.min(Math.floor(score / width), numBuckets - 1);
    buckets[idx].count++;
  }
  return buckets;
}

// ---------------------------------------------------------------------------
// Per-question summary card
// ---------------------------------------------------------------------------

function optionLabel(i: number) { return String.fromCharCode(65 + i); }

function AnswerBar({ label, count, total, correct, colorClass }: {
  label: string; count: number; total: number; correct: boolean; colorClass: string;
}) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <span className={`w-6 text-center font-mono font-bold text-sm shrink-0 ${correct ? 'text-success-ink' : 'text-ink-muted'}`}>
        {label}
      </span>
      <div className="flex-1 h-6 rounded-md border-2 border-line bg-sunken overflow-hidden">
        <div
          className={`h-full halftone transition-all duration-500 ${count > 0 ? 'border-r-2 border-line' : ''} ${colorClass}`}
          style={{ width: `${Math.max(pct, count > 0 ? 2 : 0)}%` }}
        />
      </div>
      <span className={`w-8 text-right font-mono text-sm font-bold shrink-0 ${correct ? 'text-success-ink' : 'text-ink-muted'}`}>
        {count}
      </span>
      {correct && <span className="w-4 text-success-ink text-sm font-black shrink-0" aria-label="correct">✓</span>}
      {!correct && <span className="w-4 shrink-0" />}
    </div>
  );
}

function QuestionCard({ item, index }: { item: HostQuestionSummaryItem; index: number }) {
  const { type, gradingType, prompt, promptImageId, config, answerReveal, answerDistribution, totalAnswered, totalPlayers, correctCount, avgAnswerTimeMs, pointsValue } = item;

  const typeLabel: Record<string, string> = {
    multiple_choice: 'Multiple Choice',
    true_false: 'True / False',
    fill_in_the_blank: 'Fill in the Blank',
    multi_select: 'Multi-Select',
    hotspot: 'Hotspot',
    ordering: 'Ordering',
  };

  const answeredPct = totalPlayers > 0 ? Math.round((totalAnswered / totalPlayers) * 100) : 0;
  const correctPct = totalAnswered > 0 ? Math.round((correctCount / totalAnswered) * 100) : 0;

  const reveal = answerReveal as AnswerReveal;

  function isCorrectIndex(i: number): boolean {
    if (reveal.type === 'multiple_choice') {
      return (reveal as { type: 'multiple_choice'; correctIndices: number[] }).correctIndices.includes(i);
    }
    if (reveal.type === 'multi_select') {
      return ((reveal as { type: 'multi_select'; answerPoints: number[] }).answerPoints[i] ?? 0) > 0;
    }
    return false;
  }
  function isCorrectTF(val: 'true' | 'false'): boolean {
    if (reveal.type !== 'true_false') return false;
    const rv = reveal as { type: 'true_false'; correctValue: boolean };
    return val === 'true' ? rv.correctValue : !rv.correctValue;
  }

  return (
    <Card className="w-full p-5 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-1.5 flex-wrap font-mono text-[11px] font-bold uppercase tracking-[0.15em]">
          <span className="rounded-full bg-ink px-2 py-0.5 text-canvas">Q{index + 1}</span>
          <span className="rounded-full border-2 border-line px-2 py-0.5 text-ink-muted">{typeLabel[type] ?? type}</span>
          <span className={`rounded-full px-2 py-0.5 ${gradingType === 'COMPLETENESS' ? 'bg-warning/20 text-warning-ink' : 'bg-accent/15 text-accent-ink'}`}>
            {gradingType === 'COMPLETENESS' ? 'Participation' : 'Accuracy'}
          </span>
          <span className="px-1 text-ink-muted normal-case tracking-normal">{pointsValue} {pointsValue === 1 ? 'pt' : 'pts'}</span>
        </div>
        <div className="text-right font-mono text-xs text-ink-soft shrink-0">
          <span className="text-ink-muted font-semibold">{totalAnswered}</span>/{totalPlayers} answered
          {avgAnswerTimeMs !== null && (
            <span className="ml-2 text-ink-soft">· avg {(avgAnswerTimeMs / 1000).toFixed(1)}s</span>
          )}
        </div>
      </div>

      {/* Prompt */}
      <div className="flex items-center gap-3">
        {/* T8 D8: the prompt image, small, beside the prompt. */}
        {typeof promptImageId === 'number' && (
          <ImageThumb imageId={promptImageId} alt={prompt} className="h-14 w-20 shrink-0" />
        )}
        <p className="font-display text-ink text-xl font-bold leading-snug">{prompt}</p>
      </div>

      {/* Distribution */}
      <div className="space-y-2">
        {type === 'hotspot' && (
          <HotspotView
            imageId={config.imageId}
            aspectRatio={config.aspectRatio ?? 1}
            label={`Taps for: ${prompt}`}
            rings={ringsFromReveal(reveal)}
            taps={item.taps ?? []}
            legend={{ accuracy: gradingType === 'ACCURACY', distribution: answerDistribution }}
            maxHeightVh={35}
          />
        )}
        {type === 'ordering' && (
          <OrderingView
            items={config.items ?? []}
            correctOrder={reveal.type === 'ordering' ? reveal.correctOrder : undefined}
            distribution={answerDistribution}
            meanPositions={item.meanPositions}
            accuracy={gradingType === 'ACCURACY'}
            invalidKey={gradingType === 'ACCURACY' && !(reveal.type === 'ordering' && reveal.correctOrder)}
            compact
          />
        )}
        {(type === 'multiple_choice' || type === 'multi_select') && (config.options ?? []).map((_, i) => {
          const count = answerDistribution[String(i)] ?? 0;
          const correct = isCorrectIndex(i);
          const imageId = optionImageId(config.optionImageIds, i);
          return (
            <div key={i} className="space-y-0.5">
              <div className="flex items-center gap-2 text-sm text-ink-muted">
                <span className={`font-bold ${correct ? 'text-success-ink' : ''}`}>{optionLabel(i)}.</span>
                {imageId !== null && (
                  <ImageThumb imageId={imageId} alt={`Option ${optionLabel(i)}`} className="h-8 w-12 shrink-0" />
                )}
                <span className={correct ? 'text-success-ink' : ''}>
                  {optionText(config.options, config.optionImageIds, i)}
                </span>
              </div>
              <AnswerBar
                label={optionLabel(i)}
                count={count}
                total={totalPlayers}
                correct={correct}
                colorClass={OPT_BG[i % 8]}
              />
            </div>
          );
        })}

        {type === 'true_false' && (['true', 'false'] as const).map((val) => {
          const count = answerDistribution[val] ?? 0;
          const correct = isCorrectTF(val);
          return (
            <AnswerBar
              key={val}
              label={val === 'true' ? 'T' : 'F'}
              count={count}
              total={totalPlayers}
              correct={correct}
              colorClass={val === 'true' ? 'bg-opt-4' : 'bg-opt-1'}
            />
          );
        })}

        {type === 'fill_in_the_blank' && (
          <div className="space-y-2">
            {reveal.type === 'fill_in_the_blank' && (
              <p className="text-ink-muted text-sm">
                Accepted:{' '}
                {(reveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).acceptedAnswers.map((a, i, arr) => (
                  <span key={i}>
                    <span className="text-success-ink font-mono">"{a}"</span>
                    {i < arr.length - 1 && <span className="text-ink-soft">, </span>}
                  </span>
                ))}
                {(reveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).editDistance > 0 && (
                  <span className="text-ink-soft ml-1">
                    (±{(reveal as { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }).editDistance} typo)
                  </span>
                )}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Footer stats */}
      <div className="flex flex-wrap items-center gap-4 pt-3 border-t-2 border-dashed border-line-soft text-sm">
        {gradingType === 'ACCURACY' ? (
          <>
            <span className="text-success-ink font-semibold">{correctCount} correct</span>
            <span className="text-ink-soft">·</span>
            <span className="text-ink-muted">{correctPct}% accuracy</span>
            <span className="text-ink-soft">·</span>
            <span className="text-ink-muted">{answeredPct}% responded</span>
          </>
        ) : (
          <>
            <span className="text-warning-ink font-semibold">{totalAnswered} completed</span>
            <span className="text-ink-soft">·</span>
            <span className="text-ink-muted">{answeredPct}% response rate</span>
          </>
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function GameOverPage() {
  const { gameOver } = useGame();
  const navigate = useNavigate();

  if (!gameOver) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="font-mono text-sm font-bold uppercase tracking-[0.2em] text-ink-soft">Loading final results…</p>
      </div>
    );
  }

  const { scores, playerCount, maxPossibleScore, questionSummary = [] } = gameOver;
  const buckets = buildBuckets(scores, maxPossibleScore);
  const maxCount = Math.max(...buckets.map(b => b.count), 1);

  const avg = scores.length > 0
    ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
    : 0;
  const high = scores.length > 0 ? Math.max(...scores) : 0;

  return (
    <div className="min-h-screen flex flex-col items-center p-8 gap-8">
      <div className="text-center flex flex-col items-center gap-3">
        <Stamp tone="accent" className="text-2xl">Final</Stamp>
        <h1 className="font-display text-7xl font-extrabold tracking-tight text-ink">Game over!</h1>
        <p className="font-mono text-base font-bold uppercase tracking-[0.15em] text-ink-muted">
          {playerCount} players · Max possible {maxPossibleScore.toLocaleString()} pts
        </p>
      </div>

      {/* Histogram */}
      <div className="w-full max-w-3xl">
        <p className="font-mono text-sm font-bold uppercase tracking-[0.2em] text-ink-soft text-center mb-4">Score distribution</p>
        <div className="flex items-start gap-2">
          {buckets.map((bucket, i) => {
            const heightPct = (bucket.count / maxCount) * 100;
            return (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <span className="h-6 font-mono text-ink text-base font-extrabold">
                  {bucket.count > 0 ? bucket.count : ''}
                </span>
                <div className="w-full border-b-2 border-line relative" style={{ height: '160px' }}>
                  <div
                    className="absolute bottom-0 left-0 right-0 bg-accent halftone border-2 border-b-0 border-line rounded-t-lg transition-all duration-700"
                    style={{ height: `${Math.max(heightPct, bucket.count > 0 ? 4 : 0)}%` }}
                  />
                </div>
                <span className="font-mono text-ink-soft text-[11px] text-center leading-tight">{bucket.label}</span>
              </div>
            );
          })}
        </div>
        <p className="font-mono text-ink-soft text-xs text-center mt-2">Score (points) →</p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-6 text-center">
        {([['Average', avg.toLocaleString()], ['High score', high.toLocaleString()], ['Players', String(playerCount)]] as const).map(([k, v]) => (
          <Card key={k} className="px-8 py-4">
            <p className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-ink-soft">{k}</p>
            <p className="font-mono text-4xl font-extrabold text-ink">{v}</p>
          </Card>
        ))}
      </div>

      <Button size="lg" onClick={() => navigate('/home')} className="px-10">New Game</Button>

      {/* Per-question breakdown */}
      {questionSummary.length > 0 && (
        <div className="w-full max-w-3xl space-y-4 pb-8">
          <p className="font-mono text-sm font-bold uppercase tracking-[0.2em] text-ink-soft text-center">Question breakdown</p>
          {questionSummary.map((item, i) => (
            <QuestionCard key={item.questionId} item={item} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
