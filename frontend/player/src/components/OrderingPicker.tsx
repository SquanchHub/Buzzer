// Ordering question UI (docs/plans/t7-ordering.md §6.7, O2). Presentational only: the page
// owns the tap sequence. Items never move when tapped — only their position badges change —
// so nothing jumps under the player's thumb. Colours are T9 tokens (docs/plans/t9-theming.md
// §6.3): placed = accent, out of place = warning.

interface OrderingPickerProps {
  items: string[]; // display order
  sequence: number[]; // display indices tapped so far, in tap order
  onTap: (displayIndex: number) => void;
  disabled: boolean;
}

export function OrderingPicker({ items, sequence, onTap, disabled }: OrderingPickerProps) {
  return (
    <div className="flex flex-col gap-2" role="group" aria-label="Items to put in order">
      {items.map((item, d) => {
        const position = sequence.indexOf(d);
        const placed = position >= 0;
        return (
          <button
            key={d}
            type="button"
            data-testid={`ordering-item-${d}`}
            aria-pressed={placed}
            aria-label={placed ? `${item}, position ${position + 1}` : `${item}, not placed`}
            disabled={disabled}
            onClick={() => onTap(d)}
            className={`w-full min-h-12 flex items-center gap-3 rounded-xl px-3 py-1.5 text-left text-base leading-snug font-bold border-2 transition-[transform,box-shadow,background-color] duration-75
              ${placed ? 'bg-accent border-on-fill text-on-fill shadow-none translate-x-0.5 translate-y-0.5' : 'bg-surface border-line text-ink shadow-hard-sm'}
              ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}
          >
            <span
              data-testid={`ordering-badge-${d}`}
              className={`w-8 h-8 shrink-0 rounded-full flex items-center justify-center font-mono text-base font-extrabold border-2
                ${placed ? 'bg-on-fill border-on-fill text-accent' : 'border-dashed border-line-soft'}`}
            >
              {placed ? position + 1 : ''}
            </span>
            <span className="min-w-0 break-words">{item}</span>
          </button>
        );
      })}
    </div>
  );
}

interface OrderingListProps {
  items: string[];
  order: number[]; // display indices in the order to show
  marked?: number[]; // display indices to flag as "out of place"
  title: string;
  testId: string;
}

/** A read-only numbered list, used on the results and recap screens. */
export function OrderingList({ items, order, marked = [], title, testId }: OrderingListProps) {
  return (
    <div className="w-full max-w-md text-left" data-testid={testId}>
      <p className="mb-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-ink-muted">{title}</p>
      <ol className="flex flex-col gap-1">
        {order.map((d, k) => {
          const isMarked = marked.includes(d);
          return (
            <li
              key={d}
              data-marked={isMarked || undefined}
              className={`flex items-start gap-2 rounded-lg border-2 bg-surface px-3 py-1.5 text-ink ${isMarked ? 'border-warning' : 'border-line-soft'}`}
            >
              <span className="w-5 shrink-0 font-mono font-extrabold text-ink-muted">{k + 1}</span>
              <span className="min-w-0 break-words">{items[d] ?? '?'}</span>
              {isMarked && (
                <span className="ml-auto shrink-0 rounded bg-warning/20 px-1.5 font-mono text-[10px] font-bold uppercase tracking-wider text-warning-ink">
                  out of place
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
