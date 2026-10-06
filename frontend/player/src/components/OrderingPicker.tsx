// Ordering question UI (docs/plans/t7-ordering.md §6.7, O2). Presentational only: the page
// owns the tap sequence. Items never move when tapped — only their position badges change —
// so nothing jumps under the player's thumb. Colours come from CSS variables with fallbacks
// until T9 introduces theme tokens (the hotspot pattern).

const SELECTED = 'var(--ordering-selected, #4f46e5)';
const MISPLACED = 'var(--ordering-misplaced, #f59e0b)';

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
            className={`w-full min-h-12 flex items-center gap-3 rounded-xl px-3 py-2 text-left text-base leading-snug font-semibold border-2 transition-colors
              focus:outline-none focus-visible:ring-2 focus-visible:ring-white
              ${placed ? 'text-white' : 'bg-slate-700 border-slate-600 text-slate-100'}
              ${disabled ? 'opacity-60 cursor-not-allowed' : 'active:scale-[0.98]'}`}
            style={placed ? { backgroundColor: SELECTED, borderColor: SELECTED } : undefined}
          >
            <span
              data-testid={`ordering-badge-${d}`}
              className={`w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-base font-black border-2
                ${placed ? 'bg-white border-white' : 'border-slate-500'}`}
              style={placed ? { color: SELECTED } : undefined}
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
      <p className="text-slate-400 text-sm font-semibold mb-1">{title}</p>
      <ol className="flex flex-col gap-1">
        {order.map((d, k) => {
          const isMarked = marked.includes(d);
          return (
            <li
              key={d}
              data-marked={isMarked || undefined}
              className="flex items-start gap-2 rounded-lg bg-slate-800 px-3 py-1.5 text-slate-100"
              style={isMarked ? { boxShadow: `inset 3px 0 0 ${MISPLACED}` } : undefined}
            >
              <span className="w-5 shrink-0 font-black text-slate-400">{k + 1}</span>
              <span className="min-w-0 break-words">{items[d] ?? '?'}</span>
              {isMarked && (
                <span className="ml-auto shrink-0 text-xs font-bold" style={{ color: MISPLACED }}>
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
