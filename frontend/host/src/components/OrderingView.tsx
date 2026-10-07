// Host display of an ordering question (docs/plans/t7-ordering.md §6.8). Display only.
// While the question is open the host shows just the items (OrderingItems, O11); at results
// it shows the correct order, the "out of place" distribution and the room's average order.
// Colours are theme tokens (docs/plans/t9-theming.md): perfect = success, others = accent.

/** The items in display order, large enough to read from the back of a room. */
export function OrderingItems({ items }: { items: string[] }) {
  return (
    <ol data-testid="ordering-host-items" className="w-full max-w-3xl grid gap-3 sm:grid-cols-2">
      {items.map((item, d) => (
        <li
          key={d}
          className="rounded-2xl bg-surface border-2 border-line shadow-hard px-5 py-4 text-2xl font-bold text-ink"
        >
          {item}
        </li>
      ))}
    </ol>
  );
}

interface OrderingViewProps {
  items: string[];
  correctOrder?: number[];
  distribution?: Record<string, number>; // "0".."n-1": players with that many out of place
  meanPositions?: (number | null)[];
  accuracy: boolean;
  invalidKey?: boolean; // ACCURACY but the stored key is invalid (§4.6)
  compact?: boolean; // game-over cards
}

function roomOrder(meanPositions: (number | null)[] | undefined, n: number) {
  return (meanPositions ?? [])
    .slice(0, n)
    .map((m, d) => ({ m, d }))
    .filter((e): e is { m: number; d: number } => e.m !== null)
    .sort((a, b) => a.m - b.m || a.d - b.d);
}

export function OrderingView({
  items,
  correctOrder,
  distribution = {},
  meanPositions,
  accuracy,
  invalidKey = false,
  compact = false,
}: OrderingViewProps) {
  const big = compact ? 'text-base' : 'text-2xl';
  const ranked = roomOrder(meanPositions, items.length);
  const buckets = correctOrder ? correctOrder.map((_, k) => distribution[String(k)] ?? 0) : [];
  const top = Math.max(1, ...buckets);

  return (
    <div className={`w-full ${compact ? '' : 'max-w-4xl'} grid gap-6 ${accuracy && correctOrder ? 'md:grid-cols-2' : ''}`}>
      {accuracy && invalidKey && (
        <p className="text-danger-ink font-bold">Answer key invalid</p>
      )}
      {accuracy && correctOrder && (
        <div className="space-y-4">
          <div>
            <p className="font-mono text-sm font-bold uppercase tracking-[0.2em] text-ink-soft mb-2">Correct order</p>
            <ol data-testid="ordering-host-correct-order" className="space-y-2">
              {correctOrder.map((d, k) => (
                <li key={d} className={`flex items-center gap-3 ${big} font-semibold text-ink`}>
                  <span className="w-9 h-9 shrink-0 rounded-full border-2 border-line bg-success flex items-center justify-center font-mono text-base font-black text-on-fill">
                    {k + 1}
                  </span>
                  <span>{items[d] ?? '?'}</span>
                </li>
              ))}
            </ol>
          </div>
          <div className="space-y-2">
            {buckets.map((count, k) => (
              <div key={k} data-testid={`ordering-host-bucket-${k}`} className="flex items-center gap-3">
                <span className="w-36 shrink-0 text-ink-muted text-sm font-semibold">
                  {k === 0 ? 'Perfect' : `${k} out of place`}
                </span>
                <div className="flex-1 h-8 rounded-lg border-2 border-line bg-sunken overflow-hidden">
                  <div
                    className={`h-full halftone ${count ? 'border-r-2 border-line' : ''} ${k === 0 ? 'bg-success' : 'bg-accent'}`}
                    style={{ width: `${count ? Math.max(4, (count / top) * 100) : 0}%` }}
                  />
                </div>
                <span className="w-8 text-right font-mono text-lg font-extrabold text-ink tabular-nums">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div>
        <p className="font-mono text-sm font-bold uppercase tracking-[0.2em] text-ink-soft mb-2">Room&apos;s order</p>
        {ranked.length === 0 ? (
          <p className="text-ink-soft">No answers</p>
        ) : (
          <ol data-testid="ordering-host-room-order" className="space-y-2">
            {ranked.map(({ m, d }, k) => (
              <li key={d} className={`flex items-center gap-3 ${big} text-ink`}>
                <span className="w-9 shrink-0 font-mono text-ink-muted font-black">{k + 1}</span>
                <span className="flex-1">{items[d] ?? '?'}</span>
                <span className="font-mono text-ink-soft text-sm tabular-nums">avg {m.toFixed(2)}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
