/** Grid-based scorecard mapping types */

export interface ScorecardGrid {
  rows: string[][];
}

export interface GridMapping {
  header_row: number | null;
  name_col: number;
  hole_cols: number[];
  total_col: number | null;
  out_col?: number | null;
  in_col?: number | null;
  first_player_row: number;
  last_player_row: number | null;
  first_hole_number?: number;
  par_row?: number | null;
  stroke_index_row?: number | null;
}

/** Matches backend DraftRound / save payload shapes */

export interface HoleScoreDraft {
  hole_number: number;
  score: number | null;
}

export interface PlayerStatsDraft {
  total_score: number | null;
  out_score: number | null;
  in_score: number | null;
  fairways_hit: number | null;
  fairways_possible: number | null;
  gir: number | null;
  gir_possible: number | null;
  avg_drive_distance: number | null;
  total_putts: number | null;
  scramble_successes: number | null;
  scramble_opportunities: number | null;
  sand_save_successes: number | null;
  sand_save_opportunities: number | null;
}

export interface PlayerDraft {
  name: string;
  team_name: string | null;
  hole_scores: HoleScoreDraft[];
  stats: PlayerStatsDraft;
}

export interface PredictionMeta {
  overall_confidence: number;
  field_warnings: Record<string, string>;
  has_warnings: boolean;
}

export interface DraftRound {
  date: string | null;
  course_name: string | null;
  tee_set: string | null;
  is_team_round: boolean;
  players: PlayerDraft[];
  hole_pars?: (number | null)[];
  stroke_indexes?: (number | null)[];
  raw_scorecard_text?: string | null;
  raw_stats_text?: string | null;
  scorecard_grid?: ScorecardGrid | null;
  stats_grid?: ScorecardGrid | null;
  predicted_mapping?: GridMapping | null;
  prediction_meta?: PredictionMeta | null;
  /** One grid per scorecard image (for tabbed mapper when multiple images) */
  scorecard_grids?: (ScorecardGrid | null)[] | null;
  /** One mapping per scorecard image */
  predicted_mappings?: (GridMapping | null)[] | null;
}

/** Payload for POST /api/rounds (no raw OCR text) */
export interface SaveRoundPayload {
  date: string | null;
  course_name: string | null;
  tee_set: string | null;
  is_team_round: boolean;
  players: PlayerDraft[];
  hole_pars?: (number | null)[];
  stroke_indexes?: (number | null)[];
}

/** GET /api/rounds list item */
export interface RoundSummary {
  id: number;
  date: string | null;
  course_name: string | null;
  tee_set: string | null;
  is_team_round: boolean;
  player_names: string[];
  holes_type: 9 | 18;
}

/** GET /api/analytics/lowest-round-scores */
export interface LowestRoundScoreEntry {
  player_name: string;
  best_score_to_par: number | null;
  best_total_score: number | null;
  round_id: number;
  round_date: string | null;
  course_name: string | null;
  round_par: number | null;
}

export interface PlayerCountLeaderboardEntry {
  player_name: string;
  count: number;
}

export interface PlayerRateLeaderboardEntry {
  player_name: string;
  rate: number;
}

export interface WorstHolesLeaderboardEntry {
  /** A single worst hole played - ranked from worst to best by raw score */
  player_name: string;
  score: number;
  hole_number: number;
  par: number | null;
  round_date: string | null;
  course_name: string | null;
}

export interface SinglePlayerLeaderboards {
  lowest_9_hole_round_scores: LowestRoundScoreEntry[];
  lowest_18_hole_round_scores: LowestRoundScoreEntry[];
  most_9_hole_round_wins: PlayerCountLeaderboardEntry[];
  most_18_hole_round_wins: PlayerCountLeaderboardEntry[];
  worst_holes: WorstHolesLeaderboardEntry[];
  double_bogey_plus_per_9: PlayerRateLeaderboardEntry[];
  bogeys_per_9: PlayerRateLeaderboardEntry[];
  pars_per_9: PlayerRateLeaderboardEntry[];
  birdies_per_9: PlayerRateLeaderboardEntry[];
  eagles_per_9: PlayerRateLeaderboardEntry[];
}

export interface ScoreTrendPoint {
  player_name: string;
  round_id: number;
  round_date: string;
  course_name: string | null;
  total_score: number;
  score_to_par: number | null;
  avg_si_of_round?: number | null;
}

export interface ParOrBetterTrendPoint {
  player_name: string;
  round_id: number;
  round_date: string;
  course_name: string | null;
  par_or_better_count: number;
}

export interface PerformanceTrends {
  score_trend_9: ScoreTrendPoint[];
  score_trend_18: ScoreTrendPoint[];
  par_or_better_trend_9: ParOrBetterTrendPoint[];
  par_or_better_trend_18: ParOrBetterTrendPoint[];
  avg_si_of_all_rounds_9?: number | null;
  avg_si_of_all_rounds_18?: number | null;
}

export interface TeamLeaderboardEntry {
  team_name: string;
  total_score: number;
  round_id: number;
  round_date: string | null;
  course_name: string | null;
  player_names: string[];
}

export interface TeamLeaderboards {
  lowest_scores_9: TeamLeaderboardEntry[];
  lowest_scores_18: TeamLeaderboardEntry[];
  lowest_9_hole_round_scores: LowestRoundScoreEntry[];
  lowest_18_hole_round_scores: LowestRoundScoreEntry[];
  most_9_hole_round_wins: PlayerCountLeaderboardEntry[];
  most_18_hole_round_wins: PlayerCountLeaderboardEntry[];
  worst_holes: WorstHolesLeaderboardEntry[];
  double_bogey_plus_per_9: PlayerRateLeaderboardEntry[];
  bogeys_per_9: PlayerRateLeaderboardEntry[];
  pars_per_9: PlayerRateLeaderboardEntry[];
  birdies_per_9: PlayerRateLeaderboardEntry[];
  eagles_per_9: PlayerRateLeaderboardEntry[];
}

export interface PlayerStrokeIndexHeatmapEntry {
  player_name: string;
  stroke_index: number;
  average_score_to_par: number;
  rounds_played: number;
}

export interface StrokeIndexBandEntry {
  player_name: string;
  band_label: string;
  average_score_to_par: number;
  sample_size: number;
}

export interface HoleDifficultyAnalysis {
  player_score_heatmap: PlayerStrokeIndexHeatmapEntry[];
  predicted_score_by_stroke_index: StrokeIndexBandEntry[];
}

export interface PlayerRatingEntry {
  player_name: string;
  driving: number;
  fairway: number;
  short_game: number;
  putting: number;
  rounds_played: number;
}

export interface PlayerRatings {
  players: PlayerRatingEntry[];
}

/** GET /api/rounds/{id} full round (no raw OCR) */
export interface RoundDetail {
  id: number;
  date: string | null;
  course_name: string | null;
  tee_set: string | null;
  is_team_round: boolean;
  players: PlayerDraft[];
  hole_pars?: (number | null)[] | null;
  stroke_indexes?: (number | null)[] | null;
}
