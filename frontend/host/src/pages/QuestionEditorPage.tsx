// Ported from frontend/admin/src/pages/QuestionEditorPage.tsx for the host app (T4 §6.3),
// pointed at /api/host/games/:id/*. Changes: API paths (7 call sites), the Game type
// and back link (to the game's course), a "Game details" form (PUT /host/games/:id — no
// course field, T4 D5), the page wrapper (inside ManagementLayout), and the admin copy's
// literal "\u2026"/"\u00b7"/"\u00b1" text fixed (it rendered as backslash sequences).
// Errors (e.g. the live-session 409) show inline above the content. Keep other fixes
// in sync with the admin copy. Host-only so far: the hotspot type (T7 stage B,
// docs/plans/t7-hotspot.md §7.9, §13.2), until T4 phase 3 copies HotspotEditor to admin.
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus, Trash2, ChevronUp, ChevronDown, Download } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import {
  HotspotEditor,
  HOTSPOT_ASPECT_MAX,
  HOTSPOT_ASPECT_MIN,
  HOTSPOT_DEFAULT_TARGET,
  type HotspotEditorConfig,
  type HotspotEditorTarget,
} from '../components/HotspotEditor';
import {
  OrderingEditor,
  orderingFromQuestion,
  orderingProblems,
  orderingToPayload,
  shuffleDisplay,
  type OrderingEditorState,
} from '../components/OrderingEditor';

type QuestionType = 'multiple_choice' | 'true_false' | 'fill_in_the_blank' | 'multi_select' | 'hotspot' | 'ordering';
type GradingType = 'ACCURACY' | 'COMPLETENESS';

interface Question {
  id: number;
  type: QuestionType;
  grading_type: GradingType;
  prompt: string;
  config: Record<string, unknown>;
  answer_data: Record<string, unknown>;
  time_limit_seconds: number;
  points_value: number;
  order_index: number;
}

interface Game { id: number; title: string; description: string; max_players: number; course_id: number | null }

// ---- helpers for building config/answer_data per type ----

interface McOption { text: string; points: number }

function buildMcPayload(options: McOption[], _grading: GradingType) {
  return {
    config: { options: options.map((o) => o.text) },
    answer_data: { answer_points: options.map((o) => o.points) },
  };
}

function buildTfPayload(truePoints: number, falsePoints: number) {
  return {
    config: {},
    answer_data: { answer_points: { true: truePoints, false: falsePoints } },
  };
}

function buildMsPayload(options: McOption[]) {
  return {
    config: { options: options.map((o) => o.text) },
    answer_data: { answer_points: options.map((o) => o.points) },
  };
}

interface FibAnswer { text: string; points: number }

function buildFibPayload(answers: FibAnswer[], editDistance: number) {
  return {
    config: {},
    answer_data: {
      acceptedAnswers: answers.map((a) => a.text),
      answerPoints: answers.map((a) => a.points),
      editDistance,
    },
  };
}

function hotspotFromQuestion(q: Question): { config: HotspotEditorConfig; target: HotspotEditorTarget } {
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);
  const config: HotspotEditorConfig = {};
  const imageId = num(q.config['imageId']);
  const aspectRatio = num(q.config['aspectRatio']);
  if (imageId !== undefined) config.imageId = imageId;
  if (aspectRatio !== undefined) config.aspectRatio = aspectRatio;
  // A COMPLETENESS question may have stored no target; missing keys take the defaults.
  const target = { ...HOTSPOT_DEFAULT_TARGET };
  for (const key of Object.keys(target) as (keyof HotspotEditorTarget)[]) {
    target[key] = num(q.answer_data[key]) ?? target[key];
  }
  return { config, target };
}

/** Save needs the image loaded (aspectRatio is only sent then, §13.2 G4) and in range. */
function hotspotReady(config: HotspotEditorConfig): boolean {
  const a = config.aspectRatio;
  return typeof a === 'number' && a >= HOTSPOT_ASPECT_MIN && a <= HOTSPOT_ASPECT_MAX;
}

// ---- QuestionForm subcomponent ----

interface FormState {
  type: QuestionType;
  grading: GradingType;
  prompt: string;
  timeLimitSeconds: number;
  pointsValue: number;
  // multiple_choice
  mcOptions: McOption[];
  // true_false
  tfTruePoints: number;
  tfFalsePoints: number;
  // fill_in_the_blank
  fibAnswers: FibAnswer[];
  fibEditDistance: number;
  // multi_select
  msOptions: McOption[];
  // hotspot
  hsConfig: HotspotEditorConfig;
  hsTarget: HotspotEditorTarget;
  // ordering (docs/plans/t7-ordering.md §6.9)
  ordState: OrderingEditorState;
}

const defaultForm = (): FormState => ({
  type: 'multiple_choice',
  grading: 'ACCURACY',
  prompt: '',
  timeLimitSeconds: 30,
  pointsValue: 1,
  mcOptions: [{ text: '', points: 1 }, { text: '', points: 0 }],
  tfTruePoints: 1,
  tfFalsePoints: 0,
  fibAnswers: [{ text: '', points: 1 }],
  fibEditDistance: 0,
  msOptions: [{ text: '', points: 1 }, { text: '', points: 1 }],
  hsConfig: {},
  hsTarget: { ...HOTSPOT_DEFAULT_TARGET },
  ordState: { items: ['', '', '', ''], display: shuffleDisplay(4), partialCredit: true },
});

function questionToForm(q: Question): FormState {
  const base: FormState = {
    ...defaultForm(),
    type: q.type,
    grading: q.grading_type,
    prompt: q.prompt,
    timeLimitSeconds: q.time_limit_seconds,
    pointsValue: q.points_value,
  };
  if (q.type === 'multiple_choice') {
    const opts = (q.config['options'] as string[]) ?? [];
    const pts = (q.answer_data['answer_points'] as number[]) ?? [];
    base.mcOptions = opts.map((text, i) => ({ text, points: pts[i] ?? 0 }));
  } else if (q.type === 'true_false') {
    const ap = q.answer_data['answer_points'] as { true: number; false: number } | undefined;
    base.tfTruePoints = ap?.true ?? 1;
    base.tfFalsePoints = ap?.false ?? 0;
  } else if (q.type === 'fill_in_the_blank') {
    const accepted = (q.answer_data['acceptedAnswers'] as string[]) ?? [];
    const pts = (q.answer_data['answerPoints'] as number[]) ?? [];
    base.fibAnswers = accepted.length
      ? accepted.map((text, i) => ({ text, points: pts[i] ?? 1 }))
      : [{ text: '', points: 1 }];
    base.fibEditDistance = (q.answer_data['editDistance'] as number) ?? 0;
  } else if (q.type === 'multi_select') {
    const opts = (q.config['options'] as string[]) ?? [];
    const pts = (q.answer_data['answer_points'] as number[]) ?? [];
    base.msOptions = opts.length
      ? opts.map((text, i) => ({ text, points: pts[i] ?? 1 }))
      : [{ text: '', points: 1 }, { text: '', points: 1 }];
  } else if (q.type === 'hotspot') {
    const { config, target } = hotspotFromQuestion(q);
    base.hsConfig = config;
    base.hsTarget = target;
  } else if (q.type === 'ordering') {
    base.ordState = orderingFromQuestion(q.config, q.answer_data, q.grading_type);
  }
  return base;
}

function formToPayload(form: FormState) {
  let config: Record<string, unknown> = {};
  let answer_data: Record<string, unknown> = {};
  if (form.type === 'multiple_choice') {
    const p = buildMcPayload(form.mcOptions, form.grading);
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'true_false') {
    const p = buildTfPayload(form.tfTruePoints, form.tfFalsePoints);
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'multi_select') {
    const p = buildMsPayload(form.msOptions.filter((o) => o.text.trim()));
    config = p.config;
    answer_data = p.answer_data;
  } else if (form.type === 'hotspot') {
    // The target is sent under COMPLETENESS too (unchecked there), so switching grading
    // back and forth keeps it (§13.2 G5).
    config = { ...form.hsConfig };
    answer_data = { ...form.hsTarget };
  } else if (form.type === 'ordering') {
    const p = orderingToPayload(form.ordState, form.grading);
    config = p.config;
    answer_data = p.answer_data;
  } else {
    const p = buildFibPayload(form.fibAnswers.filter((a) => a.text.trim()), form.fibEditDistance);
    config = p.config;
    answer_data = p.answer_data;
  }
  const points_value =
    form.grading === 'COMPLETENESS' || form.type === 'hotspot' || form.type === 'ordering'
      ? form.pointsValue
      : form.type === 'multiple_choice'
      ? Math.max(0, ...form.mcOptions.map((o) => o.points))
      : form.type === 'true_false'
      ? Math.max(form.tfTruePoints, form.tfFalsePoints)
      : form.type === 'multi_select'
      ? form.msOptions.reduce((sum, o) => sum + (o.points > 0 ? o.points : 0), 0)
      : Math.max(0, ...form.fibAnswers.map((a) => a.points));
  return {
    type: form.type,
    grading_type: form.grading,
    prompt: form.prompt,
    config,
    answer_data,
    time_limit_seconds: form.timeLimitSeconds,
    points_value,
  };
}

function QuestionForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial: FormState;
  onSave: (payload: ReturnType<typeof formToPayload>) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<FormState>(initial);
  // Hotspot points have no per-option source, so the field shows under both gradings (§13.2 G3).
  // Ordering has no per-option points either (§6.9).
  const showPoints = form.grading === 'COMPLETENESS' || form.type === 'hotspot' || form.type === 'ordering';
  const blockedByImage = form.type === 'hotspot' && !hotspotReady(form.hsConfig);
  const ordProblems = form.type === 'ordering' ? orderingProblems(form.ordState) : [];

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="space-y-4">
      {/* Type + grading */}
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="block text-xs text-slate-400 mb-1">Question type</label>
          <select
            data-testid="question-type-select"
            className="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 text-sm"
            value={form.type}
            onChange={(e) => set('type', e.target.value as QuestionType)}
          >
            <option value="multiple_choice">Multiple Choice</option>
            <option value="true_false">True / False</option>
            <option value="fill_in_the_blank">Fill in the Blank</option>
            <option value="multi_select">Multi-Select (Select All That Apply)</option>
            <option value="hotspot">Hotspot (tap the image)</option>
            <option value="ordering">Ordering (put items in order)</option>
          </select>
        </div>
        <div className="flex-1">
          <label className="block text-xs text-slate-400 mb-1">Grading</label>
          <select
            className="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 text-sm"
            value={form.grading}
            onChange={(e) => set('grading', e.target.value as GradingType)}
          >
            <option value="ACCURACY">Accuracy</option>
            <option value="COMPLETENESS">Completeness</option>
          </select>
        </div>
      </div>

      {/* Prompt */}
      <div>
        <label className="block text-xs text-slate-400 mb-1">Prompt</label>
        <textarea
          className="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none text-sm"
          rows={3}
          placeholder="Question text…"
          value={form.prompt}
          onChange={(e) => set('prompt', e.target.value)}
          required
        />
      </div>

      {/* Type-specific */}
      {form.type === 'multiple_choice' && (
        <div>
          <label className="block text-xs text-slate-400 mb-2">Options</label>
          {form.grading === 'ACCURACY' && (
            <div className="flex gap-2 mb-1 px-0.5">
              <span className="flex-1 text-xs text-slate-500">Answer text</span>
              <span className="w-24 text-xs text-slate-500">Points</span>
              {form.mcOptions.length > 2 && <span className="w-7" />}
            </div>
          )}
          <div className="space-y-2">
            {form.mcOptions.map((opt, i) => (
              <div key={i} className="flex gap-2 items-center">
                <Input
                  placeholder={`Option ${i + 1}`}
                  value={opt.text}
                  onChange={(e) => {
                    const opts = [...form.mcOptions];
                    opts[i] = { ...opts[i], text: e.target.value };
                    set('mcOptions', opts);
                  }}
                  className="flex-1 text-sm"
                />
                {form.grading === 'ACCURACY' && (
                  <Input
                    type="number"
                    placeholder="pts"
                    value={opt.points}
                    onChange={(e) => {
                      const opts = [...form.mcOptions];
                      opts[i] = { ...opts[i], points: Number(e.target.value) };
                      set('mcOptions', opts);
                    }}
                    className="w-24 text-sm"
                    min="0"
                    step="any"
                  />
                )}
                {form.mcOptions.length > 2 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => set('mcOptions', form.mcOptions.filter((_, j) => j !== i))}
                  >
                    <Trash2 size={12} />
                  </Button>
                )}
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => set('mcOptions', [...form.mcOptions, { text: '', points: 0 }])}
            >
              <Plus size={12} className="mr-1" /> Add option
            </Button>
          </div>
        </div>
      )}

      {form.type === 'multi_select' && (
        <div>
          <label className="block text-xs text-slate-400 mb-2">Options</label>
          {form.grading === 'ACCURACY' && (
            <div className="flex gap-2 mb-1 px-0.5">
              <span className="flex-1 text-xs text-slate-500">Answer text</span>
              <span className="w-24 text-xs text-slate-500">Points (neg = penalty)</span>
              {form.msOptions.length > 2 && <span className="w-7" />}
            </div>
          )}
          <div className="space-y-2">
            {form.msOptions.map((opt, i) => (
              <div key={i} className="flex gap-2 items-center">
                <Input
                  placeholder={`Option ${i + 1}`}
                  value={opt.text}
                  onChange={(e) => {
                    const opts = [...form.msOptions];
                    opts[i] = { ...opts[i], text: e.target.value };
                    set('msOptions', opts);
                  }}
                  className="flex-1 text-sm"
                />
                {form.grading === 'ACCURACY' && (
                  <Input
                    type="number"
                    placeholder="pts"
                    value={opt.points}
                    onChange={(e) => {
                      const opts = [...form.msOptions];
                      opts[i] = { ...opts[i], points: Number(e.target.value) };
                      set('msOptions', opts);
                    }}
                    className="w-24 text-sm"
                    step="any"
                  />
                )}
                {form.msOptions.length > 2 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => set('msOptions', form.msOptions.filter((_, j) => j !== i))}
                  >
                    <Trash2 size={12} />
                  </Button>
                )}
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => set('msOptions', [...form.msOptions, { text: '', points: 1 }])}
            >
              <Plus size={12} className="mr-1" /> Add option
            </Button>
          </div>
          {form.grading === 'ACCURACY' && (
            <p className="text-slate-500 text-xs mt-1">
              Correct options: positive pts. Distractors: negative pts (penalty). Score = sum of selected, capped at 0.
            </p>
          )}
        </div>
      )}

      {form.type === 'true_false' && form.grading === 'ACCURACY' && (
        <div>
          <label className="block text-xs text-slate-400 mb-2">Points per answer</label>
          <div className="flex gap-4">
            <div>
              <span className="text-slate-300 text-sm">True:</span>
              <Input
                type="number"
                value={form.tfTruePoints}
                onChange={(e) => set('tfTruePoints', Number(e.target.value))}
                className="w-28 mt-1 text-sm"
                min="0"
                step="any"
              />
            </div>
            <div>
              <span className="text-slate-300 text-sm">False:</span>
              <Input
                type="number"
                value={form.tfFalsePoints}
                onChange={(e) => set('tfFalsePoints', Number(e.target.value))}
                className="w-28 mt-1 text-sm"
                min="0"
                step="any"
              />
            </div>
          </div>
        </div>
      )}

      {form.type === 'fill_in_the_blank' && form.grading === 'ACCURACY' && (
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-slate-400 mb-2">Accepted answers</label>
            <div className="flex gap-2 mb-1 px-0.5">
              <span className="flex-1 text-xs text-slate-500">Answer text</span>
              <span className="w-24 text-xs text-slate-500">Points</span>
              {form.fibAnswers.length > 1 && <span className="w-7" />}
            </div>
            <div className="space-y-2">
              {form.fibAnswers.map((ans, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <Input
                    placeholder={`Answer ${i + 1}`}
                    value={ans.text}
                    onChange={(e) => {
                      const answers = [...form.fibAnswers];
                      answers[i] = { ...answers[i], text: e.target.value };
                      set('fibAnswers', answers);
                    }}
                    className="flex-1 text-sm"
                  />
                  <Input
                    type="number"
                    placeholder="pts"
                    value={ans.points}
                    onChange={(e) => {
                      const answers = [...form.fibAnswers];
                      answers[i] = { ...answers[i], points: Number(e.target.value) };
                      set('fibAnswers', answers);
                    }}
                    className="w-24 text-sm"
                    min="0"
                    step="any"
                  />
                  {form.fibAnswers.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => set('fibAnswers', form.fibAnswers.filter((_, j) => j !== i))}
                    >
                      <Trash2 size={12} />
                    </Button>
                  )}
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => set('fibAnswers', [...form.fibAnswers, { text: '', points: 1 }])}
              >
                <Plus size={12} className="mr-1" /> Add answer
              </Button>
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Edit distance tolerance (fuzzy match)</label>
            <Input
              type="number"
              value={form.fibEditDistance}
              onChange={(e) => set('fibEditDistance', Number(e.target.value))}
              className="w-28 text-sm"
              min="0"
            />
          </div>
        </div>
      )}

      {form.type === 'hotspot' && (
        <div>
          <label className="block text-xs text-slate-400 mb-2">Image and target</label>
          <HotspotEditor
            config={form.hsConfig}
            answerData={form.hsTarget}
            onChange={(config, target) => setForm((prev) => ({ ...prev, hsConfig: config, hsTarget: target }))}
          />
          {form.grading === 'COMPLETENESS' && (
            <p className="text-slate-500 text-xs mt-2">
              Target is ignored under Completeness grading: any tap earns full points.
            </p>
          )}
        </div>
      )}

      {form.type === 'ordering' && (
        <div>
          <OrderingEditor
            state={form.ordState}
            grading={form.grading}
            onChange={(ordState) => setForm((prev) => ({ ...prev, ordState }))}
          />
          {form.grading === 'COMPLETENESS' && (
            <p className="text-slate-500 text-xs mt-2">
              Completeness: any complete order earns full points. There is no correct order, which suits
              opinion rankings.
            </p>
          )}
          {form.timeLimitSeconds < 5 * form.ordState.items.length && (
            <p className="text-amber-400 text-xs mt-2">Ordering questions usually need about 5 seconds per item.</p>
          )}
        </div>
      )}

      {/* Time + points */}
      <div className="flex gap-4">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Time limit (seconds)</label>
          <Input
            type="number"
            value={form.timeLimitSeconds}
            onChange={(e) => set('timeLimitSeconds', Number(e.target.value))}
            className="w-28 text-sm"
            min="2"
            max="300"
          />
        </div>
        {showPoints && (
          <div>
            <label className="block text-xs text-slate-400 mb-1">Points value</label>
            <Input
              type="number"
              value={form.pointsValue}
              onChange={(e) => set('pointsValue', Number(e.target.value))}
              className="w-28 text-sm"
              min="0"
              max="100000"
              step="any"
            />
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <Button
          type="button"
          data-testid="question-save"
          onClick={() => onSave(formToPayload(form))}
          disabled={saving || blockedByImage || ordProblems.length > 0}
        >
          {saving ? 'Saving\u2026' : 'Save Question'}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        {blockedByImage && (
          <span className="self-center text-xs text-slate-500">Save needs a loaded image with a supported aspect ratio.</span>
        )}
        {ordProblems.length > 0 && (
          <span className="self-center text-xs text-slate-500">{ordProblems.join(' ')}</span>
        )}
      </div>
    </div>
  );
}

// ---- Game metadata (host port only; no course field — hosts can't move games, T4 D5) ----

function GameDetails({ game, onSaved, onError }: {
  game: Game;
  onSaved: (g: Game) => void;
  onError: (message: string) => void;
}) {
  const [title, setTitle] = useState(game.title);
  const [description, setDescription] = useState(game.description);
  const [maxPlayers, setMaxPlayers] = useState(String(game.max_players));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const dirty =
    title !== game.title || description !== game.description || Number(maxPlayers) !== game.max_players;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    onError('');
    try {
      const updated = await api.put<Game>(`/host/games/${game.id}`, {
        title,
        description,
        max_players: Number(maxPlayers),
      });
      onSaved(updated);
      setSaved(true);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to save game details');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader><h3 className="font-semibold text-slate-100">Game details</h3></CardHeader>
      <CardContent>
        <form onSubmit={save} className="space-y-2">
          <Input aria-label="Game title" value={title} onChange={(e) => { setTitle(e.target.value); setSaved(false); }} required maxLength={255} />
          <textarea
            aria-label="Game description"
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => { setDescription(e.target.value); setSaved(false); }}
            maxLength={5000}
            rows={2}
            className="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-300">
              Max players
              <Input type="number" min={1} max={500} value={maxPlayers} onChange={(e) => { setMaxPlayers(e.target.value); setSaved(false); }} className="w-28" />
            </label>
            <Button type="submit" size="sm" disabled={saving || !dirty || !title.trim()}>
              {saving ? 'Saving…' : 'Save details'}
            </Button>
            {saved && !dirty && <span className="text-sm text-green-400">Saved</span>}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// ---- Main page ----

export default function QuestionEditorPage() {
  const { gameId } = useParams<{ gameId: string }>();
  const navigate = useNavigate();
  const [game, setGame] = useState<Game | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);

  async function load() {
    try {
      const [g, qs] = await Promise.all([
        api.get<Game>(`/host/games/${gameId}`),
        api.get<Question[]>(`/host/games/${gameId}/questions`),
      ]);
      setGame(g);
      setQuestions(qs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [gameId]);

  async function addQuestion(payload: ReturnType<typeof formToPayload>) {
    setSaving(true);
    setError('');
    try {
      await api.post(`/host/games/${gameId}/questions`, payload);
      setShowAddForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save question');
    } finally {
      setSaving(false);
    }
  }

  async function updateQuestion(id: number, payload: ReturnType<typeof formToPayload>) {
    setSaving(true);
    setError('');
    try {
      await api.put(`/host/games/${gameId}/questions/${id}`, payload);
      setEditingId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update question');
    } finally {
      setSaving(false);
    }
  }

  async function deleteQuestion(id: number) {
    if (!confirm('Delete this question?')) return;
    try {
      await api.delete(`/host/games/${gameId}/questions/${id}`);
      setQuestions((prev) => prev.filter((q) => q.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete question');
    }
  }

  async function moveQuestion(index: number, direction: -1 | 1) {
    const newOrder = [...questions];
    const target = index + direction;
    if (target < 0 || target >= newOrder.length) return;
    [newOrder[index], newOrder[target]] = [newOrder[target], newOrder[index]];
    try {
      await api.post(`/host/games/${gameId}/questions/reorder`, {
        order: newOrder.map((q) => q.id),
      });
      setQuestions(newOrder);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reorder');
    }
  }

  async function handleExport() {
    setDownloading(true);
    setError('');
    try {
      await api.download(`/host/games/${gameId}/export`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setDownloading(false);
    }
  }

  const typeLabel: Record<QuestionType, string> = {
    multiple_choice: 'MC',
    true_false: 'T/F',
    fill_in_the_blank: 'Fill',
    multi_select: 'Multi',
    hotspot: 'Hotspot',
    ordering: 'Ordering',
  };

  if (loading) return <div className="text-slate-400">Loading…</div>;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => navigate(game?.course_id ? `/courses/${game.course_id}` : '/home')}
            className="flex items-center gap-2 text-slate-400 hover:text-slate-100 text-sm mb-2"
          >
            <ArrowLeft size={14} /> Back to course
          </button>
          <h2 className="text-2xl font-bold text-slate-100">{game?.title}</h2>
          <p className="text-slate-400 text-sm mt-0.5">{questions.length} question{questions.length !== 1 ? 's' : ''}</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleExport()}
            disabled={downloading}
          >
            <Download size={14} className="mr-1" />
            {downloading ? 'Exporting\u2026' : 'Export JSON'}
          </Button>
          <Button size="sm" onClick={() => { setShowAddForm(true); setEditingId(null); }}>
            <Plus size={14} className="mr-1" /> Add Question
          </Button>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {game && <GameDetails game={game} onSaved={setGame} onError={setError} />}

      {/* Add question form */}
      {showAddForm && (
        <Card>
          <CardHeader><h3 className="font-semibold text-slate-100">New Question</h3></CardHeader>
          <CardContent>
            <QuestionForm
              initial={defaultForm()}
              onSave={(payload) => void addQuestion(payload)}
              onCancel={() => setShowAddForm(false)}
              saving={saving}
            />
          </CardContent>
        </Card>
      )}

      {/* Question list */}
      {questions.length === 0 && !showAddForm && (
        <p className="text-slate-400">No questions yet. Add one above.</p>
      )}

      <div className="space-y-4">
        {questions.map((q, i) => (
          <Card key={q.id}>
            {editingId === q.id ? (
              <>
                <CardHeader>
                  <h3 className="font-semibold text-slate-100">Edit Question {i + 1}</h3>
                </CardHeader>
                <CardContent>
                  <QuestionForm
                    initial={questionToForm(q)}
                    onSave={(payload) => void updateQuestion(q.id, payload)}
                    onCancel={() => setEditingId(null)}
                    saving={saving}
                  />
                </CardContent>
              </>
            ) : (
              <div className="flex items-start gap-4 px-6 py-4">
                {/* Reorder buttons */}
                <div className="flex flex-col gap-1 mt-1">
                  <button
                    onClick={() => void moveQuestion(i, -1)}
                    disabled={i === 0}
                    className="text-slate-500 hover:text-slate-200 disabled:opacity-20"
                  >
                    <ChevronUp size={16} />
                  </button>
                  <button
                    onClick={() => void moveQuestion(i, 1)}
                    disabled={i === questions.length - 1}
                    className="text-slate-500 hover:text-slate-200 disabled:opacity-20"
                  >
                    <ChevronDown size={16} />
                  </button>
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-slate-500 text-xs font-mono">Q{i + 1}</span>
                    <span className="px-1.5 py-0.5 rounded text-xs bg-slate-700 text-slate-300">
                      {typeLabel[q.type]}
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-xs bg-slate-700 text-slate-300">
                      {q.grading_type}
                    </span>
                    <span className="text-slate-500 text-xs">{q.time_limit_seconds}s · {q.points_value}pts</span>
                  </div>
                  <p className="text-slate-100 text-sm leading-relaxed">{q.prompt}</p>

                  {q.type === 'multiple_choice' && (
                    <div className="mt-2 space-y-1">
                      {((q.config['options'] as string[]) ?? []).map((opt, oi) => {
                        const pts = ((q.answer_data['answer_points'] as number[]) ?? [])[oi] ?? 0;
                        return (
                          <div key={oi} className="flex items-center gap-2 text-xs">
                            <span className={pts > 0 ? 'text-green-400' : 'text-slate-500'}>
                              {pts > 0 ? '\u2713' : '\u25cb'}
                            </span>
                            <span className={pts > 0 ? 'text-slate-200' : 'text-slate-400'}>{opt}</span>
                            {pts > 0 && <span className="text-slate-500">({pts}pts)</span>}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {q.type === 'true_false' && (
                    <div className="mt-2 flex gap-4 text-xs">
                      {(['true', 'false'] as const).map((k) => {
                        const pts = (q.answer_data['answer_points'] as Record<string, number>)?.[k] ?? 0;
                        return (
                          <span key={k} className={pts > 0 ? 'text-green-400' : 'text-slate-500'}>
                            {k.charAt(0).toUpperCase() + k.slice(1)}: {pts}pts
                          </span>
                        );
                      })}
                    </div>
                  )}

                  {q.type === 'fill_in_the_blank' && (
                    <div className="mt-2 text-xs text-slate-400">
                      Accepted: {((q.answer_data['acceptedAnswers'] as string[]) ?? []).join(', ')}
                      {(q.answer_data['editDistance'] as number) > 0 && (
                        <span className="ml-2 text-slate-500">(±{q.answer_data['editDistance'] as number} edit distance)</span>
                      )}
                    </div>
                  )}

                  {q.type === 'hotspot' && (() => {
                    const { config, target } = hotspotFromQuestion(q);
                    const pct = (v: number) => `${Math.round(v * 1000) / 10}%`;
                    return (
                      <div className="mt-2 text-xs text-slate-400">
                        Image {config.imageId ?? '?'}
                        {q.grading_type === 'ACCURACY' && (
                          <span>
                            {' \u00b7 '}target ({target.x.toFixed(2)}, {target.y.toFixed(2)}){' \u00b7 '}rings{' '}
                            {pct(target.innerRadius)} / {pct(target.outerRadius)}{' \u00b7 '}partial{' '}
                            {Math.round(target.partialFraction * 100)}%
                          </span>
                        )}
                      </div>
                    );
                  })()}

                  {q.type === 'ordering' && (() => {
                    const st = orderingFromQuestion(q.config, q.answer_data, q.grading_type);
                    const short = (s: string) => (s.length > 24 ? `${s.slice(0, 23)}\u2026` : s);
                    return (
                      <div className="mt-2 text-xs text-slate-400">
                        {st.items.map(short).join(' \u2192 ')}
                        {q.grading_type === 'ACCURACY' && (
                          <span className="text-slate-500">
                            {' \u00b7 '}
                            {st.keyInvalid ? 'answer key invalid' : st.partialCredit ? 'partial credit' : 'exact order only'}
                          </span>
                        )}
                      </div>
                    );
                  })()}

                  {q.type === 'multi_select' && (
                    <div className="mt-2 space-y-1">
                      {((q.config['options'] as string[]) ?? []).map((opt, oi) => {
                        const pts = ((q.answer_data['answer_points'] as number[]) ?? [])[oi] ?? 0;
                        const isCorrect = pts > 0;
                        return (
                          <div key={oi} className="flex items-center gap-2 text-xs">
                            <span className={isCorrect ? 'text-green-400' : pts < 0 ? 'text-red-400' : 'text-slate-500'}>
                              {isCorrect ? '\u2713' : pts < 0 ? '\u2212' : '\u25cb'}
                            </span>
                            <span className={isCorrect ? 'text-slate-200' : 'text-slate-400'}>{opt}</span>
                            {pts !== 0 && <span className="text-slate-500">({pts > 0 ? '+' : ''}{pts}pts)</span>}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div className="flex gap-1 shrink-0">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => { setEditingId(q.id); setShowAddForm(false); }}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void deleteQuestion(q.id)}
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
