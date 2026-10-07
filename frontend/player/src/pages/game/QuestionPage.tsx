import { useEffect, useRef, useState, useCallback } from 'react';
import { useGame } from './GameLayout';
import { TimerBar } from '../../components/ui/TimerBar';
import { HotspotCanvas, type HotspotImage } from '../../components/HotspotCanvas';
import { ImageThumb } from '../../components/ImageThumb';
import { OrderingPicker } from '../../components/OrderingPicker';
import { Button } from '../../components/ui/button';
import { Stamp } from '../../components/ui/Stamp';
import { Check, X } from 'lucide-react';
import type { HotspotPoint } from '../../types/game';

// Riso option inks A–H (docs/plans/t9-theming.md S2): dark text on a fluorescent fill, the
// same ink per letter as the host screen. Static strings so Tailwind sees them (D10a).
const OPTION_TILE = [
  'bg-opt-1', 'bg-opt-2', 'bg-opt-3', 'bg-opt-4', 'bg-opt-5', 'bg-opt-6', 'bg-opt-7', 'bg-opt-8',
];
const OPTION_TEXT = [
  'text-opt-1', 'text-opt-2', 'text-opt-3', 'text-opt-4', 'text-opt-5', 'text-opt-6', 'text-opt-7', 'text-opt-8',
];
// Multi-select selection: an ink ring offset onto the canvas, not the focus colour (§7.2).
const SELECTED_RING = 'ring-4 ring-ink ring-offset-2 ring-offset-canvas';
const TILE =
  'halftone border-2 border-on-fill text-on-fill shadow-hard transition-[transform,box-shadow] duration-75';
const PRESS = 'active:translate-x-1 active:translate-y-1 active:shadow-none';
const SUBMIT =
  'w-full rounded-2xl border-2 border-line bg-accent py-4 font-display text-2xl font-extrabold text-on-fill shadow-hard transition-[transform,box-shadow] duration-75 active:translate-x-1 active:translate-y-1 active:shadow-none disabled:opacity-40 disabled:shadow-none disabled:cursor-not-allowed';

function optionLabel(i: number): string {
  return String.fromCharCode(65 + i); // A, B, C, … Z
}

/** The option letter in an inverted ink disc. */
function LetterDisc({ index, className = 'h-10 w-10 text-xl' }: { index: number; className?: string }) {
  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-full bg-on-fill font-mono font-extrabold ${OPTION_TEXT[index % OPTION_TEXT.length]} ${className}`}
      aria-hidden
    >
      {optionLabel(index)}
    </span>
  );
}

/** T8 D8: the image and text of an option shown as a large tap tile. Text is optional
 * (an image-only option); with no image the text fills the tile. */
function OptionTileBody({ text, imageId, index }: { text: string; imageId: number | null; index: number }) {
  return (
    <>
      {imageId !== null ? (
        <ImageThumb imageId={imageId} alt={`Option ${optionLabel(index)}`} className="h-32 w-full rounded-lg border-2 border-on-fill bg-qr" />
      ) : (
        <span className="flex h-32 w-full items-center justify-center text-center text-lg font-bold leading-tight">{text}</span>
      )}
      <span className="flex items-center gap-2">
        <LetterDisc index={index} className="h-8 w-8 text-base" />
        {imageId !== null && text.trim() && <span className="text-base font-bold leading-tight">{text}</span>}
      </span>
    </>
  );
}

function Waiting({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-3 text-center font-mono text-xs font-bold uppercase tracking-[0.2em] text-ink-muted">{children}</p>
  );
}

export default function QuestionPage() {
  const { currentQuestion, questionLocked, emitAnswer, questionImage } = useGame();
  const startTimeRef = useRef(Date.now());
  const [submitted, setSubmitted] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [hotspotPoint, setHotspotPoint] = useState<HotspotPoint | null>(null);
  // Ordering: display indices tapped so far, cleared whenever the question changes.
  const [sequence, setSequence] = useState<number[]>([]);
  const questionId = currentQuestion?.questionId;
  useEffect(() => setSequence([]), [questionId]);

  const toggleIndex = useCallback((i: number) => {
    if (submitted || questionLocked) return;
    setSelectedIndices(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  }, [submitted, questionLocked]);

  if (!currentQuestion) {
    return (
      <div className="min-h-[70dvh] flex items-center justify-center">
        <p className="font-mono text-sm font-bold uppercase tracking-[0.2em] text-ink-muted">Loading question…</p>
      </div>
    );
  }

  // T8 option images: tiles replace the list only when some option has an image.
  const optionImageIds = currentQuestion.config.optionImageIds ?? [];
  const imageOf = (i: number): number | null => {
    const id = optionImageIds[i];
    return typeof id === 'number' ? id : null;
  };
  const hasOptionImages = optionImageIds.some((id) => typeof id === 'number');

  function submit(answerData: Record<string, unknown>) {
    if (submitted) return;
    setSubmitted(true);
    emitAnswer(currentQuestion!.questionId, answerData, Date.now() - startTimeRef.current);
  }

  const questionLabel = (
    <p className="mb-2 flex items-baseline justify-between font-mono text-xs font-bold uppercase tracking-[0.2em] text-ink-muted">
      <span>Question</span>
      <span className="text-ink">
        {currentQuestion.questionNumber}<span className="text-ink-soft"> / {currentQuestion.totalQuestions}</span>
      </span>
    </p>
  );

  const lockedMsg = (
    <div className="mt-4 text-center">
      <Stamp tone="warning" className="text-sm">Locked</Stamp>
      <Waiting>Waiting for results…</Waiting>
    </div>
  );

  if (currentQuestion.type === 'multiple_choice') {
    const options = currentQuestion.config.options ?? [];
    return (
      <div className="py-5 px-4 flex flex-col gap-3.5">
        <div className="pb-1">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        {hasOptionImages ? (
          <div className="grid grid-cols-2 gap-3.5">
            {options.map((opt, i) => (
              <button
                key={i}
                disabled={submitted || questionLocked}
                onClick={() => submit({ selectedIndex: i })}
                className={`flex flex-col gap-2 rounded-2xl p-3 text-left ${TILE}
                  ${submitted || questionLocked ? 'opacity-50 shadow-none cursor-not-allowed' : PRESS}
                  ${OPTION_TILE[i % OPTION_TILE.length]}`}
              >
                <OptionTileBody text={opt} imageId={imageOf(i)} index={i} />
              </button>
            ))}
          </div>
        ) : options.map((opt, i) => (
          <button
            key={i}
            disabled={submitted || questionLocked}
            onClick={() => submit({ selectedIndex: i })}
            className={`w-full min-h-[72px] flex items-center gap-4 rounded-2xl px-4 py-3 text-left text-xl font-bold leading-tight ${TILE}
              ${submitted || questionLocked ? 'opacity-50 shadow-none cursor-not-allowed' : PRESS}
              ${OPTION_TILE[i % OPTION_TILE.length]}`}
          >
            <LetterDisc index={i} />
            <span>{opt}</span>
          </button>
        ))}
        {submitted && <Waiting>Answer submitted — waiting for results…</Waiting>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'true_false') {
    return (
      <div className="min-h-[calc(100dvh-3rem)] flex flex-col p-4 gap-4">
        <div>
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        <button
          disabled={submitted || questionLocked}
          onClick={() => submit({ selectedValue: true })}
          className={`flex flex-1 min-h-[120px] w-full items-center justify-center gap-3 rounded-3xl bg-opt-4 font-display text-5xl font-extrabold ${TILE}
            ${submitted || questionLocked ? 'opacity-50 shadow-none cursor-not-allowed' : PRESS}`}
        >
          <Check className="h-12 w-12" strokeWidth={3.5} aria-hidden /> True
        </button>
        <button
          disabled={submitted || questionLocked}
          onClick={() => submit({ selectedValue: false })}
          className={`flex flex-1 min-h-[120px] w-full items-center justify-center gap-3 rounded-3xl bg-opt-1 font-display text-5xl font-extrabold ${TILE}
            ${submitted || questionLocked ? 'opacity-50 shadow-none cursor-not-allowed' : PRESS}`}
        >
          <X className="h-12 w-12" strokeWidth={3.5} aria-hidden /> False
        </button>
        {submitted && <Waiting>Answer submitted — waiting for results…</Waiting>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'fill_in_the_blank') {
    const maxLength = currentQuestion.config.maxLength ?? 100;
    return (
      <div className="min-h-[calc(100dvh-3rem)] flex flex-col p-4 gap-5">
        <div>
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>

        {submitted ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4">
            <Stamp tone="accent" className="text-2xl">Locked in</Stamp>
            <p className="text-ink text-xl font-bold">Answer locked in!</p>
            <p className="max-w-full break-words rounded-xl border-2 border-line bg-surface px-4 py-2 font-mono text-lg text-ink">{inputValue.trim()}</p>
            <Waiting>Waiting for results…</Waiting>
          </div>
        ) : questionLocked ? (
          <div className="flex flex-col items-center gap-3 mt-4">
            {lockedMsg}
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = inputValue.trim();
              if (trimmed) submit({ text: trimmed });
            }}
            className="flex flex-1 flex-col justify-end gap-4"
          >
            <input
              type="text"
              maxLength={maxLength}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Type your answer…"
              autoFocus
              aria-label="Your answer"
              className="w-full rounded-2xl border-2 border-line bg-surface px-4 py-5 text-2xl font-bold text-ink placeholder:text-ink-soft focus:outline-none focus:ring-[3px] focus:ring-focus"
            />
            <button
              type="submit"
              disabled={!inputValue.trim()}
              className={SUBMIT}
            >
              Submit
            </button>
          </form>
        )}
      </div>
    );
  }

  if (currentQuestion.type === 'multi_select') {
    const options = currentQuestion.config.options ?? [];
    return (
      <div className="py-5 px-4 flex flex-col gap-3.5">
        <div className="pb-1">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        <p className="text-center font-mono text-xs font-bold uppercase tracking-[0.2em] text-ink-muted">Select all that apply</p>
        {hasOptionImages && (
          <div className="grid grid-cols-2 gap-3.5">
            {options.map((opt, i) => {
              const isSelected = selectedIndices.has(i);
              return (
                <button
                  key={i}
                  aria-pressed={isSelected}
                  disabled={submitted || questionLocked}
                  onClick={() => toggleIndex(i)}
                  className={`flex flex-col gap-2 rounded-2xl p-3 text-left ${TILE} ${OPTION_TILE[i % OPTION_TILE.length]}
                    ${submitted || questionLocked ? 'opacity-50 shadow-none cursor-not-allowed' : PRESS}
                    ${isSelected ? SELECTED_RING : ''}`}
                >
                  <OptionTileBody text={opt} imageId={imageOf(i)} index={i} />
                  {isSelected && <span className="font-mono text-xs font-extrabold uppercase tracking-widest">✓ Selected</span>}
                </button>
              );
            })}
          </div>
        )}
        {!hasOptionImages && options.map((opt, i) => {
          const isSelected = selectedIndices.has(i);
          return (
            <button
              key={i}
              aria-pressed={isSelected}
              disabled={submitted || questionLocked}
              onClick={() => toggleIndex(i)}
              className={`w-full min-h-[64px] flex items-center gap-4 rounded-2xl px-4 py-3 text-left text-lg font-bold leading-tight ${TILE} ${OPTION_TILE[i % OPTION_TILE.length]}
                ${submitted || questionLocked ? 'opacity-50 shadow-none cursor-not-allowed' : PRESS}
                ${isSelected ? SELECTED_RING : ''}`}
            >
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border-[3px] border-on-fill font-mono text-lg font-extrabold
                ${isSelected ? `bg-on-fill ${OPTION_TEXT[i % OPTION_TEXT.length]}` : ''}`} aria-hidden>
                {isSelected ? '✓' : optionLabel(i)}
              </span>
              <span>{opt}</span>
            </button>
          );
        })}
        {!submitted && !questionLocked && (
          <button
            disabled={selectedIndices.size === 0}
            onClick={() => submit({ selectedIndices: Array.from(selectedIndices) })}
            className={`${SUBMIT} mt-2`}
          >
            Submit ({selectedIndices.size} selected)
          </button>
        )}
        {submitted && <Waiting>Answer submitted — waiting for results…</Waiting>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'hotspot') {
    // docs/plans/t7-hotspot.md §7.7, H6: tap to place, tap again to move, then Submit.
    const image: HotspotImage =
      questionImage && questionImage.questionId === currentQuestion.questionId
        ? questionImage
        : { status: 'loading' };
    const canAnswer = !submitted && !questionLocked && image.status === 'ready';
    const submitTap = () => {
      if (!hotspotPoint) return;
      const { x, y } = hotspotPoint;
      // Any server `error` event replaces the whole game UI, so never send a bad tap.
      if (!(x >= 0 && x <= 1 && y >= 0 && y <= 1)) return;
      submit({ x, y });
    };
    return (
      <div className="py-5 px-4 flex flex-col gap-3">
        <div className="pb-1">
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        <p className="font-display text-xl font-bold leading-snug text-ink">{currentQuestion.prompt}</p>
        <HotspotCanvas
          aspectRatio={currentQuestion.config.aspectRatio ?? 1}
          image={image}
          label={currentQuestion.prompt}
          interactive={canAnswer}
          onPick={setHotspotPoint}
          marker={hotspotPoint}
        />
        {image.status === 'error' ? (
          <p className="text-center text-danger-ink text-sm font-semibold mt-2">Image unavailable — this question can't be answered.</p>
        ) : !submitted && !questionLocked ? (
          <>
            <p className="text-center font-mono text-xs font-bold uppercase tracking-[0.15em] text-ink-muted">
              {image.status === 'loading'
                ? 'Loading image…'
                : hotspotPoint
                  ? 'Tap again to move your marker'
                  : 'Tap the image to place your marker'}
            </p>
            <button
              disabled={!hotspotPoint || !canAnswer}
              onClick={submitTap}
              className={SUBMIT}
            >
              Submit
            </button>
          </>
        ) : null}
        {submitted && <Waiting>Answer submitted — waiting for results…</Waiting>}
        {!submitted && questionLocked && image.status !== 'error' && lockedMsg}
      </div>
    );
  }

  if (currentQuestion.type === 'ordering') {
    // docs/plans/t7-ordering.md §6.7, O2: tap items in order; Undo / Reset; then Submit.
    const items = currentQuestion.config.items ?? [];
    const canAnswer = !submitted && !questionLocked;
    const tap = (d: number) => {
      if (!canAnswer || sequence.includes(d)) return; // numbered items ignore taps (O2)
      setSequence(prev => (prev.includes(d) ? prev : [...prev, d]));
    };
    const submitOrder = () => {
      // Any server `error` event replaces the whole game UI, so never send a bad order.
      const isPermutation =
        sequence.length === items.length &&
        [...sequence].sort((a, b) => a - b).every((d, i) => d === i);
      if (isPermutation) submit({ order: sequence });
    };
    return (
      <div className="py-3 px-4 flex flex-col gap-2.5">
        <div>
          {questionLabel}
          <TimerBar key={currentQuestion.questionId} totalSeconds={currentQuestion.timeLimitSeconds} paused={questionLocked} />
        </div>
        <p className="font-display text-lg font-bold leading-snug text-ink">{currentQuestion.prompt}</p>
        {canAnswer && (
          <p className="font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-ink-muted">Tap in order · Undo to change</p>
        )}
        <OrderingPicker items={items} sequence={sequence} onTap={tap} disabled={!canAnswer} />
        {canAnswer && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              data-testid="ordering-undo"
              disabled={sequence.length === 0}
              onClick={() => setSequence(prev => prev.slice(0, -1))}
            >
              Undo
            </Button>
            <Button
              variant="outline"
              data-testid="ordering-reset"
              disabled={sequence.length === 0}
              onClick={() => setSequence([])}
            >
              Reset
            </Button>
            <Button
              size="lg"
              className="flex-1 font-black"
              data-testid="ordering-submit"
              disabled={sequence.length !== items.length}
              onClick={submitOrder}
            >
              Submit order
            </Button>
          </div>
        )}
        {submitted && <Waiting>Answer submitted — waiting for results…</Waiting>}
        {!submitted && questionLocked && lockedMsg}
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <p className="text-ink-muted">Unsupported question type.</p>
    </div>
  );
}
