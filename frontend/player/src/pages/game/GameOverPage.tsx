import { useNavigate } from 'react-router-dom';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';
import { HotspotCanvas, useImageUrl } from '../../components/HotspotCanvas';
import { OptionThumbs } from '../../components/OptionThumbs';
import { hasOptionImages, optionText } from '../../lib/options';
import type { PlayerAnswerReveal, QuestionSummaryItem } from '../../types/game';

function describePlayerAnswer(
  playerAnswer: QuestionSummaryItem['playerAnswer'],
  type: string,
  options: string[] | undefined,
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
  return '';
}

function QuestionRow({ item, index }: { item: QuestionSummaryItem; index: number }) {
  const options = item.config.options;
  const isCompleteness = item.answerReveal.type === 'completeness';
  const noAnswer = !item.playerAnswer;
  const isCorrect = !isCompleteness && !noAnswer && item.pointsAwarded > 0;
  const showCorrectAnswer = !isCompleteness && !isCorrect;

  const imageIds = item.config.optionImageIds;
  const playerAnswerLabel = describePlayerAnswer(item.playerAnswer, item.type, options, imageIds);
  const correctAnswerLabel = !isCompleteness
    ? describeCorrectAnswer(item.answerReveal, options, imageIds)
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
  const r = item.answerReveal;
  const correctIndices: number[] =
    r.type === 'multiple_choice' ? r.correctIndices
    : r.type === 'multi_select' ? r.answerPoints.flatMap((p, i) => (p > 0 ? [i] : []))
    : [];

  return (
    <div className="bg-slate-800/60 rounded-xl p-4 border border-slate-700/50">
      <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">Q{index + 1}</p>
      <p className="text-slate-100 text-sm font-medium leading-snug mb-3">{item.prompt}</p>
      {item.type === 'hotspot' && <HotspotRecap item={item} />}

      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-slate-500 text-xs mb-0.5">Your answer</p>
          <div className="flex items-center gap-2">
            {noAnswer ? (
              <span className="text-slate-600 text-base">—</span>
            ) : isCompleteness ? (
              <span className="text-indigo-400 text-base">●</span>
            ) : isCorrect ? (
              <span className="text-green-400 text-base">✓</span>
            ) : (
              <span className="text-red-400 text-base">✗</span>
            )}
            <span className={`text-sm font-semibold truncate ${
              noAnswer ? 'text-slate-600' :
              isCompleteness ? 'text-indigo-300' :
              isCorrect ? 'text-green-300' : 'text-red-300'
            }`}>
              {playerAnswerLabel}
            </span>
          </div>
          {withImages && <div className="mt-1"><OptionThumbs indices={chosen} imageIds={imageIds} size="h-10 w-14" /></div>}

          {showCorrectAnswer && correctAnswerLabel && (
            <p className="text-slate-500 text-xs mt-1">
              Correct: <span className="text-green-400 font-medium">{correctAnswerLabel}</span>
            </p>
          )}
          {withImages && showCorrectAnswer && (
            <div className="mt-1"><OptionThumbs indices={correctIndices} imageIds={imageIds} size="h-10 w-14" /></div>
          )}
        </div>

        <div className="text-right shrink-0">
          <p className={`text-sm font-bold ${
            item.pointsAwarded > 0 ? 'text-green-400' : 'text-slate-600'
          }`}>
            +{item.pointsAwarded.toLocaleString()}
          </p>
          <p className="text-slate-600 text-xs">pts</p>
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
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-slate-400">Loading final results…</p>
      </div>
    );
  }

  const { yourFinalScore, yourFinalRank, playerCount, questionSummary } = gameOver;

  return (
    <div className="min-h-screen flex flex-col p-4 gap-5">
      <div className="text-center pt-4 pb-2">
        <h1 className="text-4xl font-black text-slate-100">Game Over!</h1>
        <div className="mt-3 flex items-baseline justify-center gap-3">
          <span className="text-5xl font-black text-indigo-400">#{yourFinalRank}</span>
          <span className="text-slate-400 text-lg">of {playerCount}</span>
        </div>
        <p className="text-white text-2xl font-bold mt-1">
          {yourFinalScore.toLocaleString()} pts
        </p>
      </div>

      <div className="flex flex-col gap-3 pb-4">
        <p className="text-slate-500 text-xs uppercase tracking-widest text-center">Question Recap</p>
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
