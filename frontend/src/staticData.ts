import type {
  HoleDifficultyAnalysis,
  LowestRoundScoreEntry,
  PerformanceTrends,
  PlayerRatings,
  RoundDetail,
  RoundSummary,
  SinglePlayerLeaderboards,
  TeamLeaderboards,
} from "./types/round";

/** Shape of share-data.json from GET /api/export/share */
export interface ShareData {
  rounds: RoundSummary[];
  roundDetails: Record<string, RoundDetail>;
  lowestRoundScores: LowestRoundScoreEntry[];
  singlePlayerLeaderboards: SinglePlayerLeaderboards;
  performanceTrends: PerformanceTrends;
  teamLeaderboards: TeamLeaderboards;
  holeDifficulty: HoleDifficultyAnalysis;
  playerRatings: PlayerRatings;
}

let staticData: ShareData | null = null;

export function setStaticData(data: ShareData): void {
  staticData = data;
}

export function getStaticData(): ShareData | null {
  return staticData;
}
