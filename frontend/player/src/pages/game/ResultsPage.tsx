import { useGame } from './GameLayout';
import { HotspotCanvas, type HotspotImage } from '../../components/HotspotCanvas';
import { OptionThumbs } from '../../components/OptionThumbs';
import { OrderingList } from '../../components/OrderingPicker';
import { hasOptionImages, optionText } from '../../lib/options';
import type { HotspotBand, OrderingOutcome, PlayerAnswerReveal } from '../../types/game';

const HOTSPOT_LABELS: Record<HotspotBand, { text: string; className: string }> = {
  inner: { text: 'Bullseye!', className: 'text-green-400' },
  outer: { text: 'Close!', className: 'text-amber-400' },
  miss: { text: 'Miss', className: 'text-red-400' },
};

/** Rings to draw from a hotspot reveal, or null (COMPLETENESS / invalid target, §5.4). */
function hotspotRings(reveal: PlayerAnswerReveal) {
  if (reveal.type !== 'hotspot') return null;
  const { x, y, innerRadius, outerRadius } = reveal;
  if (x === undefined || y === undefined || innerRadius === undefined || outerRadius === undefined) {
    return null;
  }
  return { x, y, innerRadius, outerRadius };
}

function describeAnswer(
  lastAnswerData: Record<string, unknown> | null,
  type: string,
  options: string[] | undefined,
  imageIds?: (number | null)[],
): string | null {
  if (!lastAnswerData) return null;
  if (type === 'multiple_choice') {
    const idx = lastAnswerData.selectedIndex;
    if (typeof idx === 'number' && options && options[idx] !== undefined) {
      return `${String.fromCharCode(65 + idx)} — ${optionText(options, imageIds, idx)}`;
    }
  }
  if (type === 'true_false') {
    return lastAnswerData.selectedValue ? 'True' : 'False';
  }
  if (type === 'fill_in_the_blank') {
    return typeof lastAnswerData.text === 'string' ? lastAnswerData.text : null;
  }
  if (type === 'hotspot') {
    const { x, y } = lastAnswerData;
    return typeof x === 'number' && typeof y === 'number' ? `Tapped (${x.toFixed(2)}, ${y.toFixed(2)})` : null;
  }
  return null;
}

/** The ordering result label (docs/plans/t7-ordering.md §6.7): from the server's
 * yourOrdering, never from points, so points_value 0 and exact-only questions read right. */
function orderingLabel(
  reveal: PlayerAnswerReveal,
  answered: boolean,
  outcome: OrderingOutcome | null | undefined,
): { text: string; className: string } {
  if (reveal.type === 'completeness') return { text: 'Answer recorded!', className: 'text-indigo-400' };
  if (!answered) return { text: 'No answer', className: 'text-slate-400' };
  if (reveal.type !== 'ordering' || !reveal.correctOrder) {
    return { text: 'Not scored', className: 'text-slate-400' };
  }
  if (!outcome) return { text: 'Answer recorded', className: 'text-indigo-400' }; // don't guess
  const k = outcome.outOfPlace.length;
  if (k === 0) return { text: 'Perfect order!', className: 'text-green-400' };
  return { text: `${k} item${k === 1 ? '' : 's'} out of place`, className: 'text-amber-400' };
}

export default function ResultsPage() {
  const { questionResults, currentQuestion, lastAnswerData, questionImage } = useGame();

  if (!questionResults) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-slate-400">Loading results…</p>
      </div>
    );
  }

  const { answerReveal, yourPoints, yourScore, yourRank, playerCount } = questionResults;
  const answeredLabel = describeAnswer(
    lastAnswerData,
    currentQuestion?.type ?? '',
    currentQuestion?.config.options,
    currentQuestion?.config.optionImageIds,
  );
  const isCompleteness = answerReveal.type === 'completeness';
  const isFitb = answerReveal.type === 'fill_in_the_blank';
  const isCorrect = !isCompleteness && yourPoints > 0;
  const isHotspot = currentQuestion?.type === 'hotspot';
  // Hotspot label comes from the server's yourBand, never from points (H12, §13.1 c).
  const hotspotLabel = isCompleteness
    ? null
    : !lastAnswerData
      ? { text: 'No answer', className: 'text-slate-400' }
      : questionResults.yourBand
        ? HOTSPOT_LABELS[questionResults.yourBand]
        : { text: 'Answer recorded', className: 'text-indigo-400' }; // band unknown: don't guess
  const hotspotImage: HotspotImage =
    questionImage && currentQuestion && questionImage.questionId === currentQuestion.questionId
      ? questionImage
      : { status: 'error' };
  const ownTap =
    isHotspot && lastAnswerData && typeof lastAnswerData.x === 'number' && typeof lastAnswerData.y === 'number'
      ? { x: lastAnswerData.x, y: lastAnswerData.y, band: questionResults.yourBand ?? null }
      : null;

  const isOrdering = currentQuestion?.type === 'ordering';
  const ordItems = currentQuestion?.config.items ?? [];
  const ownOrder =
    isOrdering && lastAnswerData && Array.isArray(lastAnswerData.order)
      ? (lastAnswerData.order as number[])
      : null;
  // After a reload lastAnswerData is gone, but the server's yourOrdering still says the
  // player answered.
  const ordLabel = isOrdering
    ? orderingLabel(answerReveal, ownOrder !== null || !!questionResults.yourOrdering, questionResults.yourOrdering)
    : null;
  const correctOrder =
    answerReveal.type === 'ordering' && answerReveal.correctOrder ? answerReveal.correctOrder : null;
  // T8 D8: thumbnails of the player's choice, and of the correct choice when they missed it
  // (only for questions with option images; text-only questions look as before).
  const imageIds = currentQuestion?.config.optionImageIds;
  const withImages = hasOptionImages(imageIds);
  const chosen: number[] =
    !lastAnswerData ? []
    : typeof lastAnswerData.selectedIndex === 'number' ? [lastAnswerData.selectedIndex]
    : Array.isArray(lastAnswerData.selectedIndices) ? (lastAnswerData.selectedIndices as number[])
    : [];
  const correctIndices: number[] =
    answerReveal.type === 'multiple_choice' ? answerReveal.correctIndices
    : answerReveal.type === 'multi_select'
      ? answerReveal.answerPoints.flatMap((p, i) => (p > 0 ? [i] : []))
      : [];

  const fitbAccepted: string[] =
    isFitb && 'acceptedAnswers' in answerReveal ? answerReveal.acceptedAnswers : [];

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 gap-5 text-center">

      {/* Correct / Wrong / Recorded */}
      {ordLabel ? (
        <p data-testid="ordering-result-label" className={`${ordLabel.className} text-4xl font-black`}>
          {ordLabel.text}
        </p>
      ) : isHotspot && hotspotLabel ? (
        <p className={`${hotspotLabel.className} text-4xl font-black`}>{hotspotLabel.text}</p>
      ) : isCompleteness ? (
        <p className="text-indigo-400 text-4xl font-black">Answer recorded!</p>
      ) : isCorrect ? (
        <p className="text-green-400 text-4xl font-black">Correct!</p>
      ) : (
        <p className="text-red-400 text-4xl font-black">Incorrect</p>
      )}

      {/* What the player answered */}
      {answeredLabel && (
        <p className="text-slate-400 text-base">
          You answered: <span className="text-slate-200 font-semibold">{answeredLabel}</span>
        </p>
      )}

      {withImages && chosen.length > 0 && (
        <OptionThumbs indices={chosen} imageIds={imageIds} size="h-20 w-28" />
      )}
      {withImages && !isCompleteness && !isCorrect && correctIndices.length > 0 && (
        <div className="flex flex-col items-center gap-2">
          <p className="text-slate-400 text-base">Correct:</p>
          <OptionThumbs indices={correctIndices} imageIds={imageIds} size="h-20 w-28" />
        </div>
      )}

      {/* Hotspot: own tap and the target rings */}
      {isHotspot && currentQuestion && (
        <div className="w-full max-w-md">
          <HotspotCanvas
            aspectRatio={currentQuestion.config.aspectRatio ?? 1}
            image={hotspotImage}
            label={`Your tap and the target for: ${currentQuestion.prompt}`}
            marker={ownTap}
            rings={hotspotRings(answerReveal)}
            maxHeightVh={40}
          />
        </div>
      )}

      {/* Ordering: own order (out-of-place items marked) and the correct order */}
      {isOrdering && ownOrder && (
        <OrderingList
          items={ordItems}
          order={ownOrder}
          marked={questionResults.yourOrdering?.outOfPlace}
          title="Your order"
          testId="ordering-your-order"
        />
      )}
      {isOrdering && correctOrder && (
        <OrderingList items={ordItems} order={correctOrder} title="Correct order" testId="ordering-correct-order" />
      )}

      {/* Correct answer for FITB ACCURACY */}
      {isFitb && fitbAccepted.length > 0 && (
        <p className="text-slate-400 text-base">
          Correct: <span className="text-green-400 font-semibold">{fitbAccepted.join(' / ')}</span>
        </p>
      )}

      {/* Points for this question */}
      <p className="text-slate-100 text-3xl font-bold">
        +{yourPoints.toLocaleString()} pts
      </p>

      {/* Running total and rank */}
      <div className="mt-2 space-y-1">
        <p className="text-slate-300 text-lg">
          Total: <span className="font-bold text-white">{yourScore.toLocaleString()}</span> pts
        </p>
        <p className="text-slate-400 text-base">
          Rank <span className="font-bold text-white">#{yourRank}</span> of {playerCount}
        </p>
      </div>

      <p className="text-slate-500 text-sm mt-4">Waiting for next question…</p>
    </div>
  );
}
