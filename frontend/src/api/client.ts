const API_BASE =
  (import.meta.env.VITE_API_URL as string) || "http://127.0.0.1:8000";

import { getStaticData } from "../staticData";
import type {
  DraftRound,
  SaveRoundPayload,
  RoundSummary,
  RoundDetail,
  ScorecardGrid,
  GridMapping,
  LowestRoundScoreEntry,
  SinglePlayerLeaderboards,
  PerformanceTrends,
  TeamLeaderboards,
  HoleDifficultyAnalysis,
  PlayerRatings,
} from "../types/round";

function wrapFetchError(err: unknown, context: string): Error {
  if (err instanceof TypeError && (err.message === "Failed to fetch" || err.message === "Load failed")) {
    return new Error(`${context}: Cannot reach server at ${API_BASE}. Is the API running?`);
  }
  return err instanceof Error ? err : new Error(String(err));
}

export async function ocrDraftRound(
  scorecardFiles: File[],
  statsFile: File | null,
  imageDateHint?: string | null
): Promise<DraftRound> {
  const form = new FormData();
  for (const file of scorecardFiles) {
    form.append("scorecard_images", file);
  }
  if (statsFile) form.append("stats_image", statsFile);
  if (imageDateHint) form.append("image_date_hint", imageDateHint);
  if (scorecardFiles.length === 0 && !statsFile) {
    throw new Error("At least one image (scorecard or stats) is required.");
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/rounds/ocr-draft`, {
      method: "POST",
      body: form,
    });
  } catch (err) {
    throw wrapFetchError(err, "OCR request failed");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "OCR request failed");
  }

  return res.json() as Promise<DraftRound>;
}

export async function saveRound(payload: SaveRoundPayload): Promise<{ id: number }> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/rounds`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    throw wrapFetchError(err, "Save round failed");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Save round failed");
  }
  return res.json() as Promise<{ id: number }>;
}

export async function mapGridToDraft(
  grid: ScorecardGrid,
  mapping: GridMapping
): Promise<DraftRound> {
  const body = {
    grid,
    mapping: {
      header_row: mapping.header_row ?? null,
      name_col: mapping.name_col,
      hole_cols: mapping.hole_cols,
      total_col: mapping.total_col ?? null,
      out_col: mapping.out_col ?? null,
      in_col: mapping.in_col ?? null,
      first_player_row: mapping.first_player_row,
      last_player_row: mapping.last_player_row ?? null,
      first_hole_number: mapping.first_hole_number ?? 1,
      par_row: mapping.par_row ?? null,
      stroke_index_row: mapping.stroke_index_row ?? null,
    },
  };
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/scorecards/map-grid`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    throw wrapFetchError(err, "Apply mapping failed");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Grid mapping failed");
  }
  return res.json() as Promise<DraftRound>;
}

export async function getRounds(): Promise<RoundSummary[]> {
  if (import.meta.env.VITE_USE_STATIC_DATA === "true") {
    const data = getStaticData();
    if (data) return Promise.resolve(data.rounds);
  }
  const res = await fetch(`${API_BASE}/api/rounds`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to load rounds");
  }
  return res.json() as Promise<RoundSummary[]>;
}

export async function getRound(id: number): Promise<RoundDetail> {
  if (import.meta.env.VITE_USE_STATIC_DATA === "true") {
    const data = getStaticData();
    if (data) {
      const detail = data.roundDetails[String(id)];
      if (detail) return Promise.resolve(detail);
      throw new Error("Round not found");
    }
  }
  const res = await fetch(`${API_BASE}/api/rounds/${id}`);
  if (!res.ok) {
    if (res.status === 404) throw new Error("Round not found");
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to load round");
  }
  return res.json() as Promise<RoundDetail>;
}

export async function updateRound(id: number, payload: SaveRoundPayload): Promise<{ id: number }> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/rounds/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    throw wrapFetchError(err, "Update round failed");
  }
  if (!res.ok) {
    if (res.status === 404) throw new Error("Round not found");
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Update round failed");
  }
  return res.json() as Promise<{ id: number }>;
}

export async function deleteRound(id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/rounds/${id}`, { method: "DELETE" });
  if (!res.ok) {
    if (res.status === 404) throw new Error("Round not found");
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Delete round failed");
  }
}

// ---- Analytics endpoints ----

export async function getLowestRoundScores(): Promise<LowestRoundScoreEntry[]> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/analytics/lowest-round-scores`);
  } catch (err) {
    throw wrapFetchError(err, "Lowest round scores fetch failed");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to load lowest round scores");
  }
  return res.json() as Promise<LowestRoundScoreEntry[]>;
}

export async function getSinglePlayerLeaderboards(): Promise<SinglePlayerLeaderboards> {
  if (import.meta.env.VITE_USE_STATIC_DATA === "true") {
    const data = getStaticData();
    if (data) return Promise.resolve(data.singlePlayerLeaderboards);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/analytics/single-player-leaderboards`);
  } catch (err) {
    throw wrapFetchError(err, "Single player leaderboards fetch failed");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to load single player leaderboards");
  }
  return res.json() as Promise<SinglePlayerLeaderboards>;
}

export async function getPerformanceTrends(): Promise<PerformanceTrends> {
  if (import.meta.env.VITE_USE_STATIC_DATA === "true") {
    const data = getStaticData();
    if (data) return Promise.resolve(data.performanceTrends);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/analytics/performance-trends`);
  } catch (err) {
    throw wrapFetchError(err, "Performance trends fetch failed");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to load performance trends");
  }
  return res.json() as Promise<PerformanceTrends>;
}

export async function getTeamLeaderboards(): Promise<TeamLeaderboards> {
  if (import.meta.env.VITE_USE_STATIC_DATA === "true") {
    const data = getStaticData();
    if (data) return Promise.resolve(data.teamLeaderboards);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/analytics/team-leaderboards`);
  } catch (err) {
    throw wrapFetchError(err, "Team leaderboards fetch failed");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to load team leaderboards");
  }
  return res.json() as Promise<TeamLeaderboards>;
}

export async function getHoleDifficultyAnalysis(): Promise<HoleDifficultyAnalysis> {
  if (import.meta.env.VITE_USE_STATIC_DATA === "true") {
    const data = getStaticData();
    if (data) return Promise.resolve(data.holeDifficulty);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/analytics/hole-difficulty`);
  } catch (err) {
    throw wrapFetchError(err, "Hole difficulty fetch failed");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to load hole difficulty analysis");
  }
  return res.json() as Promise<HoleDifficultyAnalysis>;
}

export async function getPlayerRatings(): Promise<PlayerRatings> {
  if (import.meta.env.VITE_USE_STATIC_DATA === "true") {
    const data = getStaticData();
    if (data) return Promise.resolve(data.playerRatings);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/analytics/player-ratings`);
  } catch (err) {
    throw wrapFetchError(err, "Player ratings fetch failed");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to load player ratings");
  }
  return res.json() as Promise<PlayerRatings>;
}

// ---- Temporary test endpoints for perspective correction ----

export interface CornerPoint {
  x: number;
  y: number;
}

export async function detectCorners(
  file: File,
): Promise<{ corners: CornerPoint[] }> {
  const form = new FormData();
  form.append("image", file);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/test/detect-corners`, {
      method: "POST",
      body: form,
    });
  } catch (err) {
    throw wrapFetchError(err, "Corner detection failed");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Corner detection failed");
  }
  return res.json() as Promise<{ corners: CornerPoint[] }>;
}

export async function warpImage(
  file: File,
  corners: CornerPoint[],
): Promise<Blob> {
  const form = new FormData();
  form.append("image", file);
  form.append("corners", JSON.stringify(corners));
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/test/warp-image`, {
      method: "POST",
      body: form,
    });
  } catch (err) {
    throw wrapFetchError(err, "Image warp failed");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || "Image warp failed");
  }
  return res.blob();
}
