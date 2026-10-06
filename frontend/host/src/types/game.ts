export interface PlayerInfo {
  userId: string;
  displayName: string;
}

export interface SyncStatePayload {
  status: 'LOBBY' | 'IN_PROGRESS' | 'COMPLETED' | 'ABANDONED';
  players: PlayerInfo[];
  playerCount: number;
  questionPhase?: 'QUESTION' | 'RESULTS' | null;
  currentQuestion?: QuestionPayload | null;
  questionLocked?: boolean;
  timerRemainingSeconds?: number | null;
}

export interface PlayerJoinedPayload {
  userId: string;
  displayName: string;
  playerCount: number;
}

export interface PlayerLeftPayload {
  userId: string;
  playerCount: number;
}

// Hotspot (docs/plans/t7-hotspot.md §7.6). Keep in sync with the player copy.
export type HotspotBand = 'inner' | 'outer' | 'miss';

export interface HotspotConfig {
  imageId: number;
  aspectRatio: number; // image width ÷ height
}

/** One player's tap as the host sees it; band is null under COMPLETENESS. */
export interface HotspotTap {
  x: number;
  y: number;
  band: HotspotBand | null;
}

// The server sends at most this many taps per question (first N in answer order).
export const HOTSPOT_TAP_CAP = 500;

// Ordering (docs/plans/t7-ordering.md §6.6). Keep in sync with the player copy.
export interface OrderingConfig {
  items: string[]; // display order: the same shuffled order for every player
}

export interface QuestionPayload {
  questionId: number;
  questionNumber: number;
  totalQuestions: number;
  type: 'multiple_choice' | 'true_false' | 'fill_in_the_blank' | 'multi_select' | 'hotspot' | 'ordering';
  gradingType: 'ACCURACY' | 'COMPLETENESS';
  prompt: string;
  config: { options?: string[]; maxLength?: number } & Partial<HotspotConfig> & Partial<OrderingConfig>;
  timeLimitSeconds: number;
  pointsValue: number;
  editDistance?: number;
  startedAt?: string;  // ISO timestamp — only present in sync_state reconnect payloads
}

export interface AnswerStatusPayload {
  userId: string;
  displayName: string;
  answered: boolean;
  answeredCount: number;
  totalPlayers: number;
}

export interface AnswerPhaseEndedPayload {
  questionId: number;
  answeredCount: number;
  totalPlayers: number;
  allAnswered?: boolean; // true only when every player answered (not just timer expiry)
}

export interface LeaderboardEntry {
  userId: string;
  displayName: string;
  score: number;
  rank: number;
}

export type AnswerReveal =
  | { type: 'multiple_choice'; correctIndices: number[] }
  | { type: 'true_false'; correctValue: boolean }
  | { type: 'fill_in_the_blank'; acceptedAnswers: string[]; editDistance: number }
  | { type: 'completeness' }
  | { type: 'multi_select'; answerPoints: number[] }
  // Target fields are absent when the stored target is invalid (§5.4).
  | { type: 'hotspot'; x?: number; y?: number; innerRadius?: number; outerRadius?: number }
  // correctOrder is absent when the stored key is invalid (§4.6).
  | { type: 'ordering'; correctOrder?: number[] }
  | Record<string, never>;

export interface HostResultsPayload {
  questionId: number;
  answerReveal: AnswerReveal;
  answerDistribution: Record<string, number>;
  totalAnswered: number;
  totalPlayers: number;
  taps?: HotspotTap[]; // hotspot only
  // Ordering only: mean 1-based position per display index (null when no answers).
  meanPositions?: (number | null)[];
}

export interface HostQuestionSummaryItem {
  questionId: number;
  questionNumber: number;
  prompt: string;
  type: 'multiple_choice' | 'true_false' | 'fill_in_the_blank' | 'multi_select' | 'hotspot' | 'ordering';
  gradingType: 'ACCURACY' | 'COMPLETENESS';
  config: { options?: string[]; maxLength?: number } & Partial<HotspotConfig> & Partial<OrderingConfig>;
  pointsValue: number;
  answerReveal: AnswerReveal;
  answerDistribution: Record<string, number>;
  totalAnswered: number;
  totalPlayers: number;
  correctCount: number;
  avgAnswerTimeMs: number | null;
  taps?: HotspotTap[]; // hotspot only
  meanPositions?: (number | null)[]; // ordering only
}

export interface HostGameOverPayload {
  scores: number[];
  playerCount: number;
  maxPossibleScore: number;
  questionSummary: HostQuestionSummaryItem[];
}

export type HostPhase = 'lobby' | 'question' | 'results' | 'gameover';
