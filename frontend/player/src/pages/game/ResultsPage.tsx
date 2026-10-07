import { useGame } from './GameLayout';
import { Stamp, type StampTone } from '../../components/ui/Stamp';
import { HotspotCanvas, type HotspotImage } from '../../components/HotspotCanvas';
import { OptionThumbs } from '../../components/OptionThumbs';
import { OrderingList } from '../../components/OrderingPicker';
import { hasOptionImages, optionText } from '../../lib/options';
import type { HotspotBand, OrderingOutcome, PlayerAnswerReveal } from '../../types/game';

/** A verdict word and its stamp tone; `null` tone = no verdict (plain muted text). */
type Verdict = { text: string; tone: StampTone | null };

function VerdictStamp({ verdict, testId }: { verdict: Verdict; testId?: string }) {
  if (!verdict.tone) {
    return <p data-testid={testId} className="font-display text-3xl font-extrabold text-ink-muted">{verdict.text}</p>;
  }
  return (
    <Stamp data-testid={testId} tone={verdict.tone} className="text-3xl">
      {verdict.text}
    </Stamp>
  );
}

const HOTSPOT_LABELS: Record<HotspotBand, Verdict> = {
  inner: { text: 'Bullseye!', tone: 'success' },
  outer: { text: 'Close!', tone: 'warning' },
  miss: { text: 'Miss', tone: 'danger' },
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
): Verdict {
  if (reveal.type === 'completeness') return { text: 'Answer recorded!', tone: 'accent' };
  if (!answered) return { text: 'No answer', tone: null };
  if (reveal.type !== 'ordering' || !reveal.correctOrder) {
    return { text: 'Not scored', tone: null };
  }
  if (!outcome) return { text: 'Answer recorded', tone: 'accent' }; // don't guess
  const k = outcome.outOfPlace.length;
  if (k === 0) return { text: 'Perfect order!', tone: 'success' };
  return { text: `${k} item${k === 1 ? '' : 's'} out of place`, tone: 'warning' };
}

export default function ResultsPage() {
  const { questionResults, currentQuestion, lastAnswerData, questionImage } = useGame();

  if (!questionResults) {
    return (
      <div className="min-h-[70dvh] flex items-center justify-center">
        <p className="font-mono text-sm font-bold uppercase tracking-[0.2em] text-ink-muted">Loading results…</p>
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
  const hotspotLabel: Verdict | null = isCompleteness
    ? null
    : !lastAnswerData
      ? { text: 'No answer', tone: null }
      : questionResults.yourBand
        ? HOTSPOT_LABELS[questionResults.yourBand]
        : { text: 'Answer recorded', tone: 'accent' }; // band unknown: don't guess
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

  const verdict: Verdict = ordLabel
    ? ordLabel
    : isHotspot && hotspotLabel
      ? hotspotLabel
      : isCompleteness
        ? { text: 'Answer recorded!', tone: 'accent' }
        : isCorrect
          ? { text: 'Correct!', tone: 'success' }
          : { text: 'Incorrect', tone: 'danger' };

  return (
    <div className="min-h-[calc(100dvh-3rem)] flex flex-col items-center justify-center px-5 py-8 gap-5 text-center">

      {/* Correct / Wrong / Recorded, as a rubber stamp (T9 S3) */}
      <div className="py-2">
        <VerdictStamp verdict={verdict} testId={ordLabel ? 'ordering-result-label' : undefined} />
      </div>

      {/* What the player answered */}
      {answeredLabel && (
        <p className="text-ink-muted text-base">
          You answered: <span className="text-ink font-bold">{answeredLabel}</span>
        </p>
      )}

      {withImages && chosen.length > 0 && (
        <OptionThumbs indices={chosen} imageIds={imageIds} size="h-20 w-28" />
      )}
      {withImages && !isCompleteness && !isCorrect && correctIndices.length > 0 && (
        <div className="flex flex-col items-center gap-2">
          <p className="font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-ink-muted">Correct</p>
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
        <p className="text-ink-muted text-base">
          Correct: <span className="text-success-ink font-bold">{fitbAccepted.join(' / ')}</span>
        </p>
      )}

      {/* Points for this question */}
      <p className="font-mono text-5xl font-extrabold tracking-tight text-ink">
        +{yourPoints.toLocaleString()} <span className="text-xl text-ink-soft">pts</span>
      </p>

      {/* Running total and rank */}
      <div className="grid w-full max-w-xs grid-cols-2 gap-3">
        <div className="rounded-2xl border-2 border-line bg-surface px-3 py-2 shadow-hard-sm">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-ink-soft">Total</p>
          <p className="font-mono text-2xl font-extrabold text-ink">{yourScore.toLocaleString()}</p>
        </div>
        <div className="rounded-2xl border-2 border-line bg-surface px-3 py-2 shadow-hard-sm">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-ink-soft">Rank</p>
          <p className="font-mono text-2xl font-extrabold text-ink">
            #{yourRank}<span className="text-sm text-ink-soft"> / {playerCount}</span>
          </p>
        </div>
      </div>

      <p className="mt-2 font-mono text-xs font-bold uppercase tracking-[0.2em] text-ink-soft">Waiting for next question…</p>
    </div>
  );
}
