export interface SyncStatePayload {
  status: 'LOBBY' | 'IN_PROGRESS' | 'COMPLETED' | 'ABANDONED';
  playerCount: number;
  questionLocked?: boolean;
}

export interface PlayerJoinedPayload {
  playerCount: number;
}

// Hotspot (docs/plans/t7-hotspot.md §7.6). Keep in sync with the host copy.
export type HotspotBand = 'inner' | 'outer' | 'miss';

export interface HotspotConfig {
  imageId: number;
  aspectRatio: number; // image width ÷ height
}

export interface HotspotPoint {
  x: number; // fraction of image width, 0..1 from the left
  y: number; // fraction of image height, 0..1 from the top
}

// Ordering (docs/plans/t7-ordering.md §6.6). Keep in sync with the host copy.
export interface OrderingConfig {
  items: string[]; // display order: the same shuffled order for every player
}

// The player's own result (O10): computed by the server, never in the browser.
export interface OrderingOutcome {
  inOrder: number;
  total: number;
  outOfPlace: number[]; // display indices, in submission order
}

export interface QuestionPayload {
  questionId: number;
  questionNumber: number;
  totalQuestions: number;
  type: 'multiple_choice' | 'true_false' | 'fill_in_the_blank' | 'multi_select' | 'hotspot' | 'ordering';
  prompt: string;
  config: { options?: string[]; maxLength?: number } & Partial<HotspotConfig> & Partial<OrderingConfig>;
  timeLimitSeconds: number;
  pointsValue: number;
}

export interface AnswerResultPayload {
  questionId: number;
  isCorrect: boolean;
  pointsAwarded: number;
  totalScore: number;
  alreadyAnswered?: boolean;
}

export type PlayerAnswerReveal =
  | { type: 'multiple_choice'; correctIndices: number[] }
  | { type: 'true_false'; correctValue: boolean }
  | { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }
  | { type: 'completeness' }
  | { type: 'multi_select'; answerPoints: number[] }
  // Target fields are absent when the stored target is invalid (§5.4).
  | { type: 'hotspot'; x?: number; y?: number; innerRadius?: number; outerRadius?: number }
  // correctOrder is absent when the stored key is invalid (§4.6).
  | { type: 'ordering'; correctOrder?: number[] };

export interface PlayerResultsPayload {
  questionId: number;
  answerReveal: PlayerAnswerReveal;
  yourPoints: number;
  yourScore: number;
  yourRank: number;
  playerCount: number;
  // Hotspot only: own band; null if unanswered or COMPLETENESS (H12).
  yourBand?: HotspotBand | null;
  // Ordering only: own outcome; null if unanswered, COMPLETENESS or an invalid key.
  yourOrdering?: OrderingOutcome | null;
}

export interface QuestionSummaryItem {
  questionId: number;
  prompt: string;
  type: 'multiple_choice' | 'true_false' | 'fill_in_the_blank' | 'multi_select' | 'hotspot' | 'ordering';
  gradingType: 'ACCURACY' | 'COMPLETENESS';
  config: { options?: string[]; maxLength?: number } & Partial<HotspotConfig> & Partial<OrderingConfig>;
  pointsAwarded: number;
  maxPoints: number;
  answerTimeMs: number | null;
  playerAnswer: { selectedIndex?: number; selectedValue?: boolean; text?: string; selectedIndices?: number[]; x?: number; y?: number; order?: number[] } | null;
  answerReveal: PlayerAnswerReveal;
}

export interface PlayerGameOverPayload {
  yourFinalScore: number;
  yourFinalRank: number;
  playerCount: number;
  questionSummary: QuestionSummaryItem[];
}

export type PlayerPhase = 'lobby' | 'question' | 'feedback' | 'results' | 'gameover';
