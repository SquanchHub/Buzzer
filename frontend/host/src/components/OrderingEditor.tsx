// Authoring UI for ordering questions (docs/plans/t7-ordering.md §6.9). Self-contained: it
// imports only lib/utils and ui/*, so the admin copy
// (frontend/admin/src/components/OrderingEditor.tsx) differs only in import paths — keep
// the two in sync (the HotspotEditor pattern).
//
// The author types the items in the CORRECT order; the editor keeps a separate display
// order (the shuffle every player sees, O3) and maps between the two only here.
import { useEffect } from 'react';
import { ArrowDown, ArrowUp, Plus, Shuffle, Trash2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { Button } from './ui/button';
import { Input } from './ui/input';

export const ORDERING_MIN_ITEMS = 3;
export const ORDERING_MAX_ITEMS = 6;
export const ORDERING_ITEM_MAX_LEN = 80;

type Grading = 'ACCURACY' | 'COMPLETENESS';

export interface OrderingEditorState {
  items: string[]; // ACCURACY: correct order. COMPLETENESS: the order players see.
  display: number[]; // display[k] = index into items of the item shown k-th
  partialCredit: boolean;
  keyInvalid?: boolean; // the stored ACCURACY key was unusable (§4.6): warn the author
}

const normalise = (s: string) => s.split(/\s+/).filter(Boolean).join(' ');
const identity = (n: number) => Array.from({ length: n }, (_, i) => i);
const isIdentity = (seq: number[]) => seq.every((v, i) => v === i);

function isPermutation(seq: unknown, n: number): seq is number[] {
  return (
    Array.isArray(seq) &&
    seq.length === n &&
    seq.every((v) => Number.isInteger(v)) &&
    [...seq].sort((a, b) => a - b).every((v, i) => v === i)
  );
}

/** Length of the longest strictly increasing run (subsequence). O(n²); n ≤ 6. Used only
 * for the editor's shuffle heuristic — it affects no scores (the server scores). */
export function longestRunLength(seq: number[]): number {
  const best = seq.map(() => 1);
  for (let i = seq.length - 1; i >= 0; i--) {
    for (let j = i + 1; j < seq.length; j++) {
      if (seq[j] > seq[i]) best[i] = Math.max(best[i], best[j] + 1);
    }
  }
  return Math.max(0, ...best);
}

/** O3's rule: not the identity, and "submit as shown" earns at most half the credit. */
export function displayIsFair(display: number[]): boolean {
  const n = display.length;
  return !isIdentity(display) && longestRunLength(display) <= 1 + Math.floor((n - 1) / 2);
}

/** A uniformly random display order that passes displayIsFair (200 tries, then reversal). */
export function shuffleDisplay(n: number, rng: () => number = Math.random): number[] {
  for (let attempt = 0; attempt < 200; attempt++) {
    const p = identity(n);
    for (let i = n - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [p[i], p[j]] = [p[j], p[i]];
    }
    if (displayIsFair(p)) return p;
  }
  return identity(n).reverse();
}

/** Editor state from a stored question. */
export function orderingFromQuestion(
  config: Record<string, unknown>,
  answerData: Record<string, unknown>,
  grading: Grading,
): OrderingEditorState {
  const stored = Array.isArray(config['items'])
    ? (config['items'] as unknown[]).map((s) => (typeof s === 'string' ? s : ''))
    : [];
  const partialCredit = typeof answerData['partialCredit'] === 'boolean' ? answerData['partialCredit'] : true;
  if (grading === 'ACCURACY') {
    const c = answerData['correctOrder'];
    // Mirror the server's key check (§4.1): exactly these two keys, a real bool, and a
    // non-identity permutation of the stored items.
    const keys = Object.keys(answerData).sort().join(',');
    const keyOk =
      keys === 'correctOrder,partialCredit' &&
      typeof answerData['partialCredit'] === 'boolean' &&
      isPermutation(c, stored.length) &&
      !isIdentity(c);
    if (keyOk) {
      return {
        items: c.map((d) => stored[d]),
        display: identity(stored.length).map((k) => c.indexOf(k)),
        partialCredit,
      };
    }
    // Bad stored key: show the items as stored, make a fresh shuffle so a re-save is
    // valid, and tell the author to re-enter the correct order.
    const display = stored.length >= 2 ? shuffleDisplay(stored.length) : identity(stored.length);
    return { items: stored, display, partialCredit, keyInvalid: true };
  }
  return { items: stored, display: identity(stored.length), partialCredit: true };
}

/** The question's config and answer_data for a save. */
export function orderingToPayload(state: OrderingEditorState, grading: Grading) {
  const trimmed = state.items.map(normalise);
  if (grading === 'COMPLETENESS') {
    return { config: { items: trimmed }, answer_data: {} };
  }
  return {
    config: { items: state.display.map((i) => trimmed[i]) },
    answer_data: {
      correctOrder: identity(trimmed.length).map((k) => state.display.indexOf(k)),
      partialCredit: state.partialCredit,
    },
  };
}

/** Client-side copy of the server's §4.1 checks, to disable Save and say why. */
export function orderingProblems(state: OrderingEditorState): string[] {
  const problems: string[] = [];
  const items = state.items.map(normalise);
  if (items.length < ORDERING_MIN_ITEMS || items.length > ORDERING_MAX_ITEMS) {
    problems.push(`Use ${ORDERING_MIN_ITEMS} to ${ORDERING_MAX_ITEMS} items.`);
  }
  items.forEach((item, i) => {
    if (!item) problems.push(`Item ${i + 1} is empty.`);
    else if (item.length > ORDERING_ITEM_MAX_LEN) problems.push(`Item ${i + 1} is longer than ${ORDERING_ITEM_MAX_LEN} characters.`);
  });
  const seen = new Set(items.filter(Boolean).map((s) => s.toLowerCase()));
  if (seen.size !== items.filter(Boolean).length) problems.push('Items must all be different.');
  return problems;
}

interface OrderingEditorProps {
  state: OrderingEditorState;
  grading: Grading;
  onChange: (next: OrderingEditorState) => void;
}

export function OrderingEditor({ state, grading, onChange }: OrderingEditorProps) {
  const { items, display, partialCredit } = state;
  const accuracy = grading === 'ACCURACY';
  const n = items.length;

  // Switching to ACCURACY with no real shuffle yet (e.g. from COMPLETENESS) makes one.
  // Fewer than 2 items have no non-identity order, so never try (it would loop).
  useEffect(() => {
    if (accuracy && n >= 2 && (!isPermutation(display, n) || isIdentity(display))) {
      onChange({ ...state, display: shuffleDisplay(n) });
    }
  }, [accuracy, display, n]); // eslint-disable-line react-hooks/exhaustive-deps

  function setItem(i: number, value: string) {
    onChange({ ...state, items: items.map((s, j) => (j === i ? value : s)), keyInvalid: false });
  }
  function add() {
    onChange({ ...state, items: [...items, ''], display: shuffleDisplay(n + 1), keyInvalid: false });
  }
  function remove(i: number) {
    const next = items.filter((_, j) => j !== i);
    onChange({ ...state, items: next, display: shuffleDisplay(next.length), keyInvalid: false });
  }
  /** Swap item i with its neighbour; both keep their display slots unless O3 breaks. */
  function move(i: number, delta: -1 | 1) {
    const j = i + delta;
    if (j < 0 || j >= n) return;
    const nextItems = [...items];
    [nextItems[i], nextItems[j]] = [nextItems[j], nextItems[i]];
    let nextDisplay = display.map((v) => (v === i ? j : v === j ? i : v));
    if (accuracy && !displayIsFair(nextDisplay)) nextDisplay = shuffleDisplay(n);
    onChange({ ...state, items: nextItems, display: nextDisplay, keyInvalid: false });
  }

  return (
    <div className="space-y-3">
      {state.keyInvalid && accuracy && (
        <p className="rounded-lg border border-danger bg-danger/15 px-3 py-2 text-sm text-danger-ink">
          The stored answer key is invalid. Re-enter the items in the correct order.
        </p>
      )}
      <div>
        <label className="block text-xs text-ink-muted mb-1">
          {accuracy ? 'Items in the correct order (first → last)' : 'Items (players see them in this order)'}
        </label>
        <div className="space-y-2">
          {items.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="w-5 text-right text-xs font-mono text-ink-soft">{i + 1}</span>
              <Input
                data-testid={`ordering-editor-item-${i}`}
                aria-label={`Item ${i + 1}`}
                value={item}
                maxLength={ORDERING_ITEM_MAX_LEN}
                placeholder={`Item ${i + 1}`}
                onChange={(e) => setItem(i, e.target.value)}
                className="flex-1 text-sm"
              />
              <button
                type="button"
                aria-label={`Move item ${i + 1} up`}
                disabled={i === 0}
                onClick={() => move(i, -1)}
                className="p-1 text-ink-muted hover:text-ink disabled:opacity-20"
              >
                <ArrowUp size={14} />
              </button>
              <button
                type="button"
                aria-label={`Move item ${i + 1} down`}
                disabled={i === n - 1}
                onClick={() => move(i, 1)}
                className="p-1 text-ink-muted hover:text-ink disabled:opacity-20"
              >
                <ArrowDown size={14} />
              </button>
              <button
                type="button"
                aria-label={`Remove item ${i + 1}`}
                disabled={n <= ORDERING_MIN_ITEMS}
                onClick={() => remove(i)}
                className="p-1 text-ink-muted hover:text-danger-ink disabled:opacity-20"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="mt-2"
          data-testid="ordering-editor-add"
          disabled={n >= ORDERING_MAX_ITEMS}
          onClick={add}
        >
          <Plus size={12} className="mr-1" /> Add item
        </Button>
        <p className="text-ink-soft text-xs mt-1">
          Say which end comes first in the prompt, e.g. &ldquo;earliest first&rdquo;.
        </p>
      </div>

      {accuracy && (
        <>
          <label className="flex items-start gap-2 text-sm text-ink">
            <input
              type="checkbox"
              data-testid="ordering-editor-partial"
              checked={partialCredit}
              onChange={(e) => onChange({ ...state, partialCredit: e.target.checked })}
              className="mt-0.5"
            />
            <span>
              Partial credit for nearly-right orders
              <span className="block text-xs text-ink-soft">
                {partialCredit
                  ? `Each item out of place costs 1/${Math.max(n - 1, 1)} of the points.`
                  : 'Only the exact order earns points.'}
              </span>
            </span>
          </label>
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-ink-muted">Players see:</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                data-testid="ordering-editor-shuffle"
                onClick={() => onChange({ ...state, display: shuffleDisplay(n) })}
              >
                <Shuffle size={12} className="mr-1" /> Shuffle again
              </Button>
            </div>
            <ol data-testid="ordering-editor-preview" className="space-y-1">
              {display.map((idx, k) => (
                <li
                  key={k}
                  className={cn(
                    'rounded-md bg-surface px-3 py-1.5 text-sm',
                    items[idx]?.trim() ? 'text-ink' : 'text-ink-soft italic',
                  )}
                >
                  {items[idx]?.trim() || `(item ${idx + 1})`}
                </li>
              ))}
            </ol>
          </div>
        </>
      )}
    </div>
  );
}
