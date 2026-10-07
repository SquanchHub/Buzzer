import { useNavigate } from 'react-router-dom';
import { useGame } from './GameLayout';
import { Stamp } from '../../components/ui/Stamp';
import { Button } from '../../components/ui/button';
import { HotspotCanvas, useImageUrl } from '../../components/HotspotCanvas';
import { OptionThumbs } from '../../components/OptionThumbs';
import { hasOptionImages, optionText } from '../../lib/options';
import type { PlayerAnswerReveal, QuestionSummaryItem } from '../../types/game';

function describePlayerAnswer(
  playerAnswer: QuestionSummaryItem['playerAnswer'],
  type: string,
  options: string[] | undefined,
  items: string[] | undefined,
  imageIds?: (number | null)[],
): string {
  if (!playerAnswer) return 'No answer';
  if (type === 'multiple_choice') {
    const idx = playerAnswer.selectedIndex;
    if (typeof idx === 'number' && options && options[idx] !== undefined) {
      return `${String.fromCharCode(65 + idx)} — ${optionText(options, imageIds, idx)}`;
    }
    return '?';
  }
  if (type === 'true_false') {
    return playerAnswer.selectedValue ? 'True' : 'False';
  }
  if (type === 'fill_in_the_blank') {
    return typeof playerAnswer.text === 'string' ? playerAnswer.text : '—';
  }
  if (type === 'multi_select') {
    const indices = playerAnswer.selectedIndices;
    if (!indices || indices.length === 0) return 'No selection';
    if (options) return indices.map(i => `${String.fromCharCode(65 + i)} — ${optionText(options, imageIds, i)}`).join(', ');
    return indices.map(i => String.fromCharCode(65 + i)).join(', ');
  }
  if (type === 'hotspot') {
    const { x, y } = playerAnswer;
    return typeof x === 'number' && typeof y === 'number' ? `Tapped (${x.toFixed(2)}, ${y.toFixed(2)})` : '—';
  }
  if (type === 'ordering') {
    const order = playerAnswer.order;
    return Array.isArray(order) && items ? order.map(d => items[d] ?? '?').join(' → ') : '—';
  }
  return '—';
}

/** Small recap canvas: own tap + target rings, no band label (§7.7). */
function HotspotRecap({ item }: { item: QuestionSummaryItem }) {
  const image = useImageUrl(item.config.imageId);
  const r = item.answerReveal;
  const rings =
    r.type === 'hotspot' &&
    r.x !== undefined && r.y !== undefined && r.innerRadius !== undefined && r.outerRadius !== undefined
      ? { x: r.x, y: r.y, innerRadius: r.innerRadius, outerRadius: r.outerRadius }
      : null;
  const a = item.playerAnswer;
  const marker = a && typeof a.x === 'number' && typeof a.y === 'number' ? { x: a.x, y: a.y } : null;
  return (
    <div className="mb-3">
      <HotspotCanvas
        aspectRatio={item.config.aspectRatio ?? 1}
        image={image}
        label={`Your tap and the target for: ${item.prompt}`}
        marker={marker}
        rings={rings}
        maxHeightVh={30}
      />
    </div>
  );
}

function describeCorrectAnswer(
  answerReveal: PlayerAnswerReveal,
  options: string[] | undefined,
  items: string[] | undefined,
  imageIds?: (number | null)[],
): string {
  if (answerReveal.type === 'multiple_choice') {
    const indices = answerReveal.correctIndices;
    if (options) {
      return indices.map(i => `${String.fromCharCode(65 + i)} — ${optionText(options, imageIds, i)}`).join(', ');
    }
    return indices.map(i => String.fromCharCode(65 + i)).join(', ');
  }
  if (answerReveal.type === 'true_false') {
    return answerReveal.correctValue ? 'True' : 'False';
  }
  if (answerReveal.type === 'fill_in_the_blank') {
    const label = answerReveal.acceptedAnswers.join(' / ');
    return answerReveal.editDistance > 0 ? `${label} (±${answerReveal.editDistance})` : label;
  }
  if (answerReveal.type === 'multi_select') {
    const correct = answerReveal.answerPoints
      .map((p, i) => ({ p, i }))
      .filter(({ p }) => p > 0)
      .map(({ i }) => options ? `${String.fromCharCode(65 + i)} — ${optionText(options, imageIds, i)}` : String.fromCharCode(65 + i));
    return correct.join(', ');
  }
  if (answerReveal.type === 'ordering' && answerReveal.correctOrder && items) {
    return answerReveal.correctOrder.map(d => items[d] ?? '?').join(' → ');
  }
  return '';
}

function QuestionRow({ item, index }: { item: QuestionSummaryItem; index: number }) {
  const options = item.config.options;
  const isCompleteness = item.answerReveal.type === 'completeness';
  const noAnswer = !item.playerAnswer;
  // Ordering: "correct" means the exact order (O6); partial credit still shows the answer.
  const r = item.answerReveal;
  const exactOrder =
    r.type === 'ordering' && !!r.correctOrder &&
    JSON.stringify(item.playerAnswer?.order) === JSON.stringify(r.correctOrder);
  const isCorrect =
    !isCompleteness && !noAnswer && (item.type === 'ordering' ? exactOrder : item.pointsAwarded > 0);
  const showCorrectAnswer = !isCompleteness && !isCorrect;

  const imageIds = item.config.optionImageIds;
  const playerAnswerLabel = describePlayerAnswer(item.playerAnswer, item.type, options, item.config.items, imageIds);
  const correctAnswerLabel = !isCompleteness
    ? describeCorrectAnswer(item.answerReveal, options, item.config.items, imageIds)
    : '';
  // T8 D8: thumbnails of the player's choice and the correct choice (questions with option
  // images only; text-only rows look as before).
  const withImages = hasOptionImages(imageIds);
  const a = item.playerAnswer;
  const chosen: number[] =
    !a ? []
    : typeof a.selectedIndex === 'number' ? [a.selectedIndex]
    : Array.isArray(a.selectedIndices) ? a.selectedIndices
    : [];
  const correctIndices: number[] =
    r.type === 'multiple_choice' ? r.correctIndices
    : r.type === 'multi_select' ? r.answerPoints.flatMap((p, i) => (p > 0 ? [i] : []))
    : [];

  return (
    <div className="bg-surface rounded-2xl p-4 border-2 border-line shadow-hard-sm">
      <p className="mb-1 font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-ink-soft">Q{index + 1}</p>
      <p className="text-ink text-base font-bold leading-snug mb-3">{item.prompt}</p>
      {item.type === 'hotspot' && <HotspotRecap item={item} />}

      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="mb-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-ink-soft">Your answer</p>
          <div className="flex items-center gap-2">
            {noAnswer ? (
              <span className="text-ink-soft text-base">—</span>
            ) : isCompleteness ? (
              <span className="text-accent-ink text-base">●</span>
            ) : isCorrect ? (
              <span className="text-success-ink text-base">✓</span>
            ) : (
              <span className="text-danger-ink text-base">✗</span>
            )}
            {/* An ordering answer is a whole sequence: wrap it rather than cut it off. */}
            <span className={`text-sm font-semibold ${item.type === 'ordering' ? 'break-words' : 'truncate'} ${
              noAnswer ? 'text-ink-soft' :
              isCompleteness ? 'text-accent-ink' :
              isCorrect ? 'text-success-ink' : 'text-danger-ink'
            }`}>
              {playerAnswerLabel}
            </span>
          </div>
          {withImages && <div className="mt-1"><OptionThumbs indices={chosen} imageIds={imageIds} size="h-10 w-14" /></div>}

          {showCorrectAnswer && correctAnswerLabel && (
            <p className="text-ink-soft text-xs mt-1">
              Correct: <span className="text-success-ink font-medium">{correctAnswerLabel}</span>
            </p>
          )}
          {withImages && showCorrectAnswer && (
            <div className="mt-1"><OptionThumbs indices={correctIndices} imageIds={imageIds} size="h-10 w-14" /></div>
          )}
        </div>

        <div className="text-right shrink-0">
          <p className={`font-mono text-lg font-extrabold ${
            item.pointsAwarded > 0 ? 'text-success-ink' : 'text-ink-soft'
          }`}>
            +{item.pointsAwarded.toLocaleString()}
          </p>
          <p className="text-ink-soft text-xs">pts</p>
        </div>
      </div>
    </div>
  );
}

export default function GameOverPage() {
  const { gameOver } = useGame();
  const navigate = useNavigate();

  if (!gameOver) {
    return (
      <div className="min-h-[70dvh] flex items-center justify-center">
        <p className="font-mono text-sm font-bold uppercase tracking-[0.2em] text-ink-muted">Loading final results…</p>
      </div>
    );
  }

  const { yourFinalScore, yourFinalRank, playerCount, questionSummary } = gameOver;

  return (
    <div className="flex flex-col p-4 gap-5">
      <div className="text-center pt-4 pb-2 flex flex-col items-center gap-4">
        <Stamp tone="accent" className="text-2xl">Final</Stamp>
        <h1 className="font-display text-5xl font-extrabold tracking-tight text-ink">Game over!</h1>
        <div className="w-full max-w-xs rounded-3xl border-2 border-line bg-accent px-5 py-4 text-on-fill shadow-hard halftone">
          <p className="font-mono text-[11px] font-bold uppercase tracking-[0.25em]">Your rank</p>
          <p className="font-mono text-7xl font-extrabold leading-none">
            #{yourFinalRank}<span className="text-2xl"> / {playerCount}</span>
          </p>
          <p className="mt-2 font-mono text-xl font-extrabold">{yourFinalScore.toLocaleString()} pts</p>
        </div>
      </div>

      <div className="flex flex-col gap-3 pb-4">
        <p className="text-center font-mono text-[11px] font-bold uppercase tracking-[0.25em] text-ink-soft">Question recap</p>
        {questionSummary.map((item, i) => (
          <QuestionRow key={item.questionId} item={item} index={i} />
        ))}
      </div>

      <div className="pb-6 flex justify-center">
        <Button
          variant="outline"
          onClick={() => {
            localStorage.removeItem('token');
            navigate('/join');
          }}
        >
          Play Again
        </Button>
      </div>
    </div>
  );
}
