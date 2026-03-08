import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getHoleDifficultyAnalysis,
  getPerformanceTrends,
  getPlayerRatings,
  getSinglePlayerLeaderboards,
  getTeamLeaderboards,
} from "../api/client";
import type {
  HoleDifficultyAnalysis,
  LowestRoundScoreEntry,
  ParOrBetterTrendPoint,
  PerformanceTrends,
  PlayerCountLeaderboardEntry,
  PlayerRateLeaderboardEntry,
  PlayerRatingEntry,
  PlayerRatings,
  ScoreTrendPoint,
  SinglePlayerLeaderboards,
  StrokeIndexBandEntry,
  TeamLeaderboards,
  WorstHolesLeaderboardEntry,
} from "../types/round";

const PLAYER_COLORS = [
  "#2563eb",
  "#16a34a",
  "#dc2626",
  "#9333ea",
  "#ea580c",
  "#0891b2",
  "#ca8a04",
  "#4f46e5",
];

type SectionId =
  | "single-player"
  | "performance-trends"
  | "team-leaderboards"
  | "hole-difficulty"
  | "player-ratings";

const ANALYTICS_SECTIONS: Array<{ id: SectionId; title: string; description: string }> = [
  {
    id: "single-player",
    title: "Player Leaderboards",
    description: "Best rounds and per-hole scoring.",
  },
  {
    id: "team-leaderboards",
    title: "Team Leaderboards",
    description: "Lowest winning team scores.",
  },
  {
    id: "performance-trends",
    title: "Performance Trends",
    description: "Score and par-or-better trends over time.",
  },
  {
    id: "hole-difficulty",
    title: "Hole Difficulty",
    description: "Scoring by hole difficulty (stroke index).",
  },
  {
    id: "player-ratings",
    title: "Player Ratings",
    description: "Skills profile across driving, fairway, short game, and putting.",
  },
];

function formatDate(d: string | null): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return d;
  }
}

function formatSignedNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value > 0) return `+${value}`;
  return String(value);
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

function getPlayerColor(index: number): string {
  return PLAYER_COLORS[index % PLAYER_COLORS.length];
}

function useSectionData<T>(loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loader()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load data");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [loader]);

  return { data, loading, error };
}

function SectionCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div
      style={{
        padding: "1.25rem",
        borderRadius: "0.75rem",
        border: "1px solid #e5e7eb",
        backgroundColor: "#ffffff",
      }}
    >
      <div style={{ marginBottom: "0.9rem" }}>
        <strong style={{ fontSize: "1rem" }}>{title}</strong>
        {subtitle && <p style={{ margin: "0.35rem 0 0", color: "#6b7280", fontSize: "0.875rem" }}>{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

function SectionMessage({ text, tone = "neutral" }: { text: string; tone?: "neutral" | "error" }) {
  return (
    <p
      style={{
        margin: 0,
        color: tone === "error" ? "#dc2626" : "#6b7280",
        fontStyle: tone === "neutral" ? "italic" : "normal",
        padding: "0.5rem 0",
      }}
    >
      {text}
    </p>
  );
}

function LoadingOrError({
  loading,
  error,
}: {
  loading: boolean;
  error: string | null;
}) {
  if (loading) return <SectionMessage text="Loading analytics…" />;
  if (error) return <SectionMessage text={error} tone="error" />;
  return null;
}

function HolesToggle({
  value,
  onChange,
}: {
  value: 9 | 18;
  onChange: (v: 9 | 18) => void;
}) {
  return (
    <div style={{ display: "flex", gap: "0.25rem", marginBottom: "1rem" }}>
      <button
        type="button"
        onClick={() => onChange(9)}
        style={{
          padding: "0.4rem 0.75rem",
          borderRadius: "0.5rem",
          border: `1px solid ${value === 9 ? "#2563eb" : "#e5e7eb"}`,
          background: value === 9 ? "#eff6ff" : "#ffffff",
          color: value === 9 ? "#2563eb" : "#6b7280",
          fontWeight: value === 9 ? 600 : 400,
          cursor: "pointer",
        }}
      >
        9 Holes
      </button>
      <button
        type="button"
        onClick={() => onChange(18)}
        style={{
          padding: "0.4rem 0.75rem",
          borderRadius: "0.5rem",
          border: `1px solid ${value === 18 ? "#2563eb" : "#e5e7eb"}`,
          background: value === 18 ? "#eff6ff" : "#ffffff",
          color: value === 18 ? "#2563eb" : "#6b7280",
          fontWeight: value === 18 ? 600 : 400,
          cursor: "pointer",
        }}
      >
        18 Holes
      </button>
    </div>
  );
}

function WorstHolesList({
  title,
  subtitle,
  entries,
}: {
  title: string;
  subtitle: string;
  entries: WorstHolesLeaderboardEntry[];
}) {
  if (entries.length === 0) {
    return (
      <SectionCard title={title} subtitle={subtitle}>
        <SectionMessage text="No hole scores yet for this leaderboard." />
      </SectionCard>
    );
  }

  return (
    <SectionCard title={title} subtitle={subtitle}>
      <ol style={{ margin: 0, paddingLeft: "1.25rem", listStyle: "decimal" }}>
        {entries.map((entry, index) => (
          <li
            key={`${entry.player_name}-${entry.round_date}-${entry.hole_number}-${index}`}
            style={{
              padding: "0.4rem 0",
              fontSize: "0.9rem",
              color: "#374151",
            }}
          >
            <strong>{entry.player_name}</strong> — {entry.score}
            {entry.par != null && ` (Par ${entry.par})`}
            {` — Hole ${entry.hole_number}`}
            {entry.round_date && ` — ${formatDate(entry.round_date)}`}
            {entry.course_name && ` — ${entry.course_name}`}
          </li>
        ))}
      </ol>
    </SectionCard>
  );
}

function LeaderboardBarChart({
  title,
  subtitle,
  rows,
  positiveIsBetter = true,
  valueFormatter = (value: number) => String(value),
}: {
  title: string;
  subtitle: string;
  rows: Array<{ player_name: string; value: number }>;
  positiveIsBetter?: boolean;
  valueFormatter?: (value: number) => string;
}) {
  if (rows.length === 0) {
    return (
      <SectionCard title={title} subtitle={subtitle}>
        <SectionMessage text="No data yet for this leaderboard." />
      </SectionCard>
    );
  }

  const chartHeight = Math.max(220, rows.length * 42 + 40);

  return (
    <SectionCard title={title} subtitle={subtitle}>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f0f0f0" />
          <XAxis type="number" tick={{ fontSize: 12 }} axisLine={{ stroke: "#e5e7eb" }} tickLine={false} />
          <YAxis
            type="category"
            dataKey="player_name"
            width={90}
            tick={{ fontSize: 13, fontWeight: 500 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip formatter={(value: number | string) => valueFormatter(Number(value))} />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={28}>
            {rows.map((entry, index) => (
              <Cell
                key={`${entry.player_name}-${index}`}
                fill={positiveIsBetter ? getPlayerColor(index) : entry.value > 0 ? "#dc2626" : "#2563eb"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </SectionCard>
  );
}

function LowestRoundsList({
  title,
  subtitle,
  entries,
}: {
  title: string;
  subtitle: string;
  entries: LowestRoundScoreEntry[];
}) {
  if (entries.length === 0) {
    return (
      <SectionCard title={title} subtitle={subtitle}>
        <SectionMessage text="No rounds yet." />
      </SectionCard>
    );
  }

  return (
    <SectionCard title={title} subtitle={subtitle}>
      <ol style={{ margin: 0, paddingLeft: "1.25rem", listStyle: "decimal" }}>
        {entries.map((entry, index) => (
          <li
            key={`${entry.player_name}-${entry.round_id}-${index}`}
            style={{
              padding: "0.4rem 0",
              fontSize: "0.9rem",
              color: "#374151",
            }}
          >
            <strong>{entry.player_name}</strong> — {entry.best_total_score ?? "—"}
            {entry.best_score_to_par != null && (
              <span style={{ color: "#6b7280" }}> ({formatSignedNumber(entry.best_score_to_par)})</span>
            )}
            {entry.round_date && ` — ${formatDate(entry.round_date)}`}
            {entry.course_name && ` — ${entry.course_name}`}
          </li>
        ))}
      </ol>
    </SectionCard>
  );
}

function buildTimelineRows<T extends { player_name: string; round_id: number; round_date: string; course_name: string | null }>(
  points: T[],
  valueKey: keyof T,
) {
  const players = Array.from(new Set(points.map((point) => point.player_name)));
  const colorMap = Object.fromEntries(players.map((player, index) => [player, getPlayerColor(index)]));
  const grouped = new Map<number, Record<string, string | number | null>>();

  [...points]
    .sort((left, right) => {
      const leftTime = new Date(left.round_date).getTime();
      const rightTime = new Date(right.round_date).getTime();
      return leftTime - rightTime || left.round_id - right.round_id;
    })
    .forEach((point) => {
      const row = grouped.get(point.round_id) ?? {
        round_id: point.round_id,
        round_date: point.round_date,
        course_name: point.course_name,
        label: formatDate(point.round_date),
      };
      const val = point[valueKey];
      row[point.player_name] = val == null ? null : Number(val);
      grouped.set(point.round_id, row);
    });

  return {
    rows: Array.from(grouped.values()),
    players,
    colorMap,
  };
}

function SinglePlayerLeaderboardsSection() {
  const [holesMode, setHolesMode] = useState<9 | 18>(9);
  const { data, loading, error } = useSectionData<SinglePlayerLeaderboards>(getSinglePlayerLeaderboards);
  if (loading || error) return <LoadingOrError loading={loading} error={error} />;
  if (!data) return null;

  const lowestScores = holesMode === 9 ? data.lowest_9_hole_round_scores : data.lowest_18_hole_round_scores;
  const mostWins = holesMode === 9 ? data.most_9_hole_round_wins : data.most_18_hole_round_wins;

  const rateFormatter = (v: number) => `${v.toFixed(2)} per 9 holes`;

  return (
    <div>
      <HolesToggle value={holesMode} onChange={setHolesMode} />
      <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
        <LowestRoundsList
          title={holesMode === 9 ? "Best 9-Hole Rounds" : "Best 18-Hole Rounds"}
          subtitle="Top 5 individual rounds."
          entries={lowestScores}
        />
        <LeaderboardBarChart
          title={holesMode === 9 ? "Most 9-Hole Wins" : "Most 18-Hole Wins"}
          subtitle="Round wins by lowest score."
          rows={mostWins.map((entry: PlayerCountLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.count,
          }))}
        />
        <WorstHolesList
          title="Worst Holes"
          subtitle="Top 5 worst holes by score."
          entries={data.worst_holes}
        />
        <LeaderboardBarChart
          title="Double Bogey+ per 9 Holes"
          subtitle="Average per 9 holes."
          rows={data.double_bogey_plus_per_9.map((entry: PlayerRateLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.rate,
          }))}
          positiveIsBetter={false}
          valueFormatter={rateFormatter}
        />
        <LeaderboardBarChart
          title="Bogeys per 9 Holes"
          subtitle="Average per 9 holes."
          rows={data.bogeys_per_9.map((entry: PlayerRateLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.rate,
          }))}
          positiveIsBetter={false}
          valueFormatter={rateFormatter}
        />
        <LeaderboardBarChart
          title="Pars per 9 Holes"
          subtitle="Average per 9 holes."
          rows={data.pars_per_9.map((entry: PlayerRateLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.rate,
          }))}
          valueFormatter={rateFormatter}
        />
        <LeaderboardBarChart
          title="Birdies per 9 Holes"
          subtitle="Average per 9 holes."
          rows={data.birdies_per_9.map((entry: PlayerRateLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.rate,
          }))}
          valueFormatter={rateFormatter}
        />
        <LeaderboardBarChart
          title="Eagles per 9 Holes"
          subtitle="Average per 9 holes."
          rows={data.eagles_per_9.map((entry: PlayerRateLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.rate,
          }))}
          valueFormatter={rateFormatter}
        />
      </div>
    </div>
  );
}

function TrendTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; color?: string; payload?: { course_name?: string | null } }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        backgroundColor: "#ffffff",
        border: "1px solid #e5e7eb",
        borderRadius: "0.5rem",
        padding: "0.75rem 1rem",
        fontSize: "0.875rem",
        boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
      }}
    >
      <div style={{ fontWeight: 600 }}>{label}</div>
      <div style={{ color: "#6b7280", marginBottom: "0.35rem" }}>{payload[0]?.payload?.course_name || "Unknown course"}</div>
      {payload
        .filter((entry) => entry.value !== undefined && entry.value !== null)
        .map((entry) => (
          <div key={entry.name} style={{ color: entry.color || "#111827" }}>
            {entry.name}: <strong>{entry.value}</strong>
          </div>
        ))}
    </div>
  );
}

function TrendChart({
  title,
  subtitle,
  rows,
  players,
  colorMap,
  yDomain,
  referenceLineAtZero = false,
}: {
  title: string;
  subtitle: string;
  rows: Array<Record<string, string | number | null>>;
  players: string[];
  colorMap: Record<string, string>;
  yDomain?: [number, number];
  referenceLineAtZero?: boolean;
}) {
  if (rows.length === 0 || players.length === 0) {
    return (
      <SectionCard title={title} subtitle={subtitle}>
        <SectionMessage text="No round data yet." />
      </SectionCard>
    );
  }

  return (
    <SectionCard title={title} subtitle={subtitle}>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={rows} margin={{ top: 10, right: 24, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} domain={yDomain ?? ["auto", "auto"]} />
          <Tooltip content={<TrendTooltip />} />
          <Legend />
          {referenceLineAtZero && <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 2" strokeWidth={1.5} />}
          {players.map((player) => (
            <Line
              key={player}
              type="monotone"
              dataKey={player}
              stroke={colorMap[player]}
              strokeWidth={2}
              dot={{ r: 4 }}
              activeDot={{ r: 6 }}
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </SectionCard>
  );
}

function PerformanceTrendsSection() {
  const [holesMode, setHolesMode] = useState<9 | 18>(9);
  const { data, loading, error } = useSectionData<PerformanceTrends>(getPerformanceTrends);
  if (loading || error) return <LoadingOrError loading={loading} error={error} />;
  if (!data) return null;

  const scoreTrendPoints = holesMode === 9 ? data.score_trend_9 : data.score_trend_18;
  const parTrendPoints = holesMode === 9 ? data.par_or_better_trend_9 : data.par_or_better_trend_18;
  const scoreTrend = buildTimelineRows<ScoreTrendPoint>(scoreTrendPoints, "total_score");
  const parTrend = buildTimelineRows<ParOrBetterTrendPoint>(parTrendPoints, "par_or_better_count");
  const parYDomain: [number, number] = holesMode === 9 ? [0, 9] : [0, 18];

  return (
    <div>
      <HolesToggle value={holesMode} onChange={setHolesMode} />
      <div style={{ display: "grid", gap: "1rem" }}>
        <TrendChart
          title={holesMode === 9 ? "Score Trend (9 Holes)" : "Score Trend (18 Holes)"}
          subtitle="Total score over time."
          rows={scoreTrend.rows}
          players={scoreTrend.players}
          colorMap={scoreTrend.colorMap}
        />
        <TrendChart
          title={holesMode === 9 ? "Par or Better (9 Holes)" : "Par or Better (18 Holes)"}
          subtitle="Holes at par or better over time."
          rows={parTrend.rows}
          players={parTrend.players}
          colorMap={parTrend.colorMap}
          yDomain={parYDomain}
        />
      </div>
    </div>
  );
}

function TeamLeaderboardsSection() {
  const [holesMode, setHolesMode] = useState<9 | 18>(9);
  const { data, loading, error } = useSectionData<TeamLeaderboards>(getTeamLeaderboards);
  if (loading || error) return <LoadingOrError loading={loading} error={error} />;
  if (!data) return null;

  const lowestRoundScores = holesMode === 9 ? data.lowest_9_hole_round_scores : data.lowest_18_hole_round_scores;
  const mostWins = holesMode === 9 ? data.most_9_hole_round_wins : data.most_18_hole_round_wins;
  const lowestScores = holesMode === 9 ? data.lowest_scores_9 : data.lowest_scores_18;

  const rateFormatter = (v: number) => `${v.toFixed(2)} per 9 holes`;

  return (
    <div>
      <HolesToggle value={holesMode} onChange={setHolesMode} />
      <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
        <LowestRoundsList
          title={holesMode === 9 ? "Best Team 9-Hole Rounds" : "Best Team 18-Hole Rounds"}
          subtitle="Top 5 team rounds."
          entries={lowestRoundScores}
        />
        <LeaderboardBarChart
          title={holesMode === 9 ? "Most 9-Hole Team Wins" : "Most 18-Hole Team Wins"}
          subtitle="Round wins by lowest team score."
          rows={mostWins.map((entry: PlayerCountLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.count,
          }))}
        />
        <WorstHolesList
          title="Worst Holes (Teams)"
          subtitle="Top 5 worst holes by score."
          entries={data.worst_holes}
        />
        <LeaderboardBarChart
          title="Double Bogey+ per 9 Holes"
          subtitle="Average per 9 holes."
          rows={data.double_bogey_plus_per_9.map((entry: PlayerRateLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.rate,
          }))}
          positiveIsBetter={false}
          valueFormatter={rateFormatter}
        />
        <LeaderboardBarChart
          title="Bogeys per 9 Holes"
          subtitle="Average per 9 holes."
          rows={data.bogeys_per_9.map((entry: PlayerRateLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.rate,
          }))}
          positiveIsBetter={false}
          valueFormatter={rateFormatter}
        />
        <LeaderboardBarChart
          title="Pars per 9 Holes"
          subtitle="Average per 9 holes."
          rows={data.pars_per_9.map((entry: PlayerRateLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.rate,
          }))}
          valueFormatter={rateFormatter}
        />
        <LeaderboardBarChart
          title="Birdies per 9 Holes"
          subtitle="Average per 9 holes."
          rows={data.birdies_per_9.map((entry: PlayerRateLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.rate,
          }))}
          valueFormatter={rateFormatter}
        />
        <LeaderboardBarChart
          title="Eagles per 9 Holes"
          subtitle="Average per 9 holes."
          rows={data.eagles_per_9.map((entry: PlayerRateLeaderboardEntry) => ({
            player_name: entry.player_name,
            value: entry.rate,
          }))}
          valueFormatter={rateFormatter}
        />
      </div>
      {lowestScores.length > 0 && (
        <SectionCard title="Winning Team Details" subtitle="All rounds in the leaderboard.">
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
              <thead>
                <tr style={{ backgroundColor: "#f9fafb", borderBottom: "1px solid #e5e7eb" }}>
                  <th style={{ textAlign: "left", padding: "0.75rem" }}>Team</th>
                  <th style={{ textAlign: "left", padding: "0.75rem" }}>Date</th>
                  <th style={{ textAlign: "left", padding: "0.75rem" }}>Course</th>
                  <th style={{ textAlign: "left", padding: "0.75rem" }}>Players</th>
                  <th style={{ textAlign: "right", padding: "0.75rem" }}>Score</th>
                </tr>
              </thead>
              <tbody>
                {lowestScores.map((entry) => (
                  <tr key={`${entry.round_id}-${entry.team_name}`} style={{ borderBottom: "1px solid #e5e7eb" }}>
                    <td style={{ padding: "0.75rem" }}>{entry.team_name}</td>
                    <td style={{ padding: "0.75rem" }}>{formatDate(entry.round_date)}</td>
                    <td style={{ padding: "0.75rem" }}>{entry.course_name || "—"}</td>
                    <td style={{ padding: "0.75rem" }}>{entry.player_names.join(", ") || "—"}</td>
                    <td style={{ padding: "0.75rem", textAlign: "right", fontWeight: 600 }}>{entry.total_score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}

function heatmapColor(scoreToPar: number | null): string {
  if (scoreToPar === null) return "#f3f4f6";
  if (scoreToPar < 0) {
    const intensity = clamp(Math.abs(scoreToPar) / 3, 0.2, 1);
    return `rgba(22, 163, 74, ${intensity})`;
  }
  if (scoreToPar > 0) {
    const intensity = clamp(scoreToPar / 3, 0.2, 1);
    return `rgba(220, 38, 38, ${intensity})`;
  }
  return "#93c5fd";
}

function HoleDifficultySection() {
  const { data, loading, error } = useSectionData<HoleDifficultyAnalysis>(getHoleDifficultyAnalysis);
  if (loading || error) return <LoadingOrError loading={loading} error={error} />;
  if (!data) return null;

  const players = Array.from(new Set(data.player_score_heatmap.map((entry) => entry.player_name)));
  const heatmapLookup = new Map<string, { average_score_to_par: number; rounds_played: number }>();
  data.player_score_heatmap.forEach((entry) => {
    heatmapLookup.set(`${entry.player_name}:${entry.stroke_index}`, {
      average_score_to_par: entry.average_score_to_par,
      rounds_played: entry.rounds_played,
    });
  });

  const strokeBands = ["1-4", "5-8", "9-12", "13-16"];
  const strokePlayers = Array.from(new Set(data.predicted_score_by_stroke_index.map((entry) => entry.player_name)));
  const strokeColorMap = Object.fromEntries(strokePlayers.map((player, index) => [player, getPlayerColor(index)]));
  const strokeRows = strokeBands.map((band) => {
    const row: Record<string, string | number> = { band_label: band };
    data.predicted_score_by_stroke_index
      .filter((entry: StrokeIndexBandEntry) => entry.band_label === band)
      .forEach((entry) => {
        row[entry.player_name] = entry.average_score_to_par;
      });
    return row;
  });

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <SectionCard
        title="Score by Hole Difficulty"
        subtitle="Score to par by stroke index. Green is under par, red is over."
      >
        {players.length === 0 ? (
          <SectionMessage text="No stroke-index data yet." />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "separate", borderSpacing: 4, minWidth: 920 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "0.5rem", color: "#6b7280" }}>Player</th>
                  {Array.from({ length: 18 }, (_, index) => (
                    <th key={index + 1} style={{ padding: "0.5rem", color: "#6b7280", fontWeight: 500 }} title={`Stroke index ${index + 1}`}>
                      SI {index + 1}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {players.map((player) => (
                  <tr key={player}>
                    <td style={{ padding: "0.5rem", fontWeight: 600, whiteSpace: "nowrap" }}>{player}</td>
                    {Array.from({ length: 18 }, (_, index) => {
                      const strokeIndex = index + 1;
                      const entry = heatmapLookup.get(`${player}:${strokeIndex}`) ?? null;
                      return (
                        <td
                          key={`${player}-${strokeIndex}`}
                          title={
                            entry
                              ? `${player}, stroke index ${strokeIndex}: ${formatSignedNumber(entry.average_score_to_par)} over ${entry.rounds_played} holes`
                              : `${player}, stroke index ${strokeIndex}: no data`
                          }
                          style={{
                            minWidth: 42,
                            height: 42,
                            textAlign: "center",
                            borderRadius: 8,
                            backgroundColor: heatmapColor(entry?.average_score_to_par ?? null),
                            color: entry && entry.average_score_to_par > 1 ? "#ffffff" : "#111827",
                            fontSize: "0.78rem",
                            fontWeight: 600,
                          }}
                        >
                          {entry ? formatSignedNumber(entry.average_score_to_par) : "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ display: "flex", gap: "1rem", marginTop: "0.75rem", fontSize: "0.82rem", color: "#6b7280" }}>
          <span>Green: below par</span>
          <span>Blue: even par</span>
          <span>Red: above par</span>
        </div>
      </SectionCard>

      <SectionCard
        title="Score by Difficulty Group"
        subtitle="Average score to par by difficulty bands."
      >
        {strokePlayers.length === 0 ? (
          <SectionMessage text="No stroke-index data yet." />
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={strokeRows} margin={{ top: 10, right: 24, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="band_label" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} tickFormatter={(value: number) => formatSignedNumber(value)} />
              <Tooltip formatter={(value: number | string) => formatSignedNumber(Number(value))} />
              <Legend />
              <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 2" strokeWidth={1.5} />
              {strokePlayers.map((player) => (
                <Bar key={player} dataKey={player} fill={strokeColorMap[player]} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </SectionCard>
    </div>
  );
}

function PlayerCard({ player }: { player: PlayerRatingEntry }) {
  const initial = player.player_name.charAt(0).toUpperCase();
  const stats = [
    { label: "Driving", value: player.driving },
    { label: "Fairway", value: player.fairway },
    { label: "Short Game", value: player.short_game },
    { label: "Putting", value: player.putting },
  ];
  return (
    <div
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: "0.75rem",
        padding: "1.25rem",
        backgroundColor: "#ffffff",
        maxWidth: 320,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "1rem",
      }}
    >
      <div
        style={{
          width: 90,
          height: 90,
          borderRadius: "50%",
          backgroundColor: "#e5e7eb",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "2rem",
          fontWeight: 700,
          color: "#4b5563",
        }}
      >
        {initial}
      </div>
      <div style={{ fontSize: "1.125rem", fontWeight: 600, color: "#111827" }}>{player.player_name}</div>
      <div style={{ width: "100%", display: "grid", gap: "0.5rem" }}>
        {stats.map(({ label, value }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontSize: "0.875rem", color: "#6b7280", minWidth: 80 }}>{label}</span>
            <div
              style={{
                flex: 1,
                height: 8,
                backgroundColor: "#f3f4f6",
                borderRadius: 4,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${value}%`,
                  height: "100%",
                  backgroundColor: "#2563eb",
                  borderRadius: 4,
                }}
              />
            </div>
            <span style={{ fontSize: "0.875rem", fontWeight: 600, minWidth: 32, textAlign: "right" }}>
              {value.toFixed(0)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PlayerRatingsSection() {
  const { data, loading, error } = useSectionData<PlayerRatings>(getPlayerRatings);
  const [selectedPlayer, setSelectedPlayer] = useState<string>("");
  useEffect(() => {
    if (!data?.players.length) return;
    if (!selectedPlayer || !data.players.some((entry) => entry.player_name === selectedPlayer)) {
      setSelectedPlayer(data.players[0].player_name);
    }
  }, [data, selectedPlayer]);

  if (loading || error) return <LoadingOrError loading={loading} error={error} />;
  if (!data) return null;
  if (data.players.length === 0) return <SectionMessage text="No player data yet." />;

  const selectedEntry =
    data.players.find((entry: PlayerRatingEntry) => entry.player_name === selectedPlayer) ?? data.players[0];
  const radarData = [
    { metric: "Driving", rating: selectedEntry.driving },
    { metric: "Fairway", rating: selectedEntry.fairway },
    { metric: "Short Game", rating: selectedEntry.short_game },
    { metric: "Putting", rating: selectedEntry.putting },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <SectionCard title="Player Profile" subtitle="Skills ratings across key categories.">
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap", marginBottom: "1rem" }}>
          <label style={{ display: "grid", gap: "0.35rem", fontSize: "0.875rem", color: "#4b5563" }}>
            Player
            <select
              value={selectedEntry.player_name}
              onChange={(event) => setSelectedPlayer(event.target.value)}
              style={{
                padding: "0.5rem 0.75rem",
                borderRadius: "0.5rem",
                border: "1px solid #d1d5db",
                minWidth: 180,
              }}
            >
              {data.players.map((entry) => (
                <option key={entry.player_name} value={entry.player_name}>
                  {entry.player_name}
                </option>
              ))}
            </select>
          </label>
          <div style={{ fontSize: "0.875rem", color: "#6b7280", alignSelf: "end" }}>
            Rounds used: <strong>{selectedEntry.rounds_played}</strong>
          </div>
        </div>
        <div style={{ display: "flex", gap: "1.5rem", alignItems: "flex-start", flexWrap: "wrap" }}>
          <PlayerCard player={selectedEntry} />
          <div style={{ flex: 1, minWidth: 280 }}>
            <ResponsiveContainer width="100%" height={340}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="metric" />
                <PolarRadiusAxis domain={[0, 100]} tickCount={6} />
                <Radar
                  name={selectedEntry.player_name}
                  dataKey="rating"
                  stroke="#2563eb"
                  fill="#2563eb"
                  fillOpacity={0.35}
                />
                <Tooltip formatter={(value: number | string) => `${Number(value).toFixed(1)}`} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Rating Table" subtitle="Scores by category.">
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.9rem" }}>
            <thead>
              <tr style={{ backgroundColor: "#f9fafb", borderBottom: "1px solid #e5e7eb" }}>
                <th style={{ textAlign: "left", padding: "0.75rem" }}>Player</th>
                <th style={{ textAlign: "right", padding: "0.75rem" }}>Driving</th>
                <th style={{ textAlign: "right", padding: "0.75rem" }}>Fairway</th>
                <th style={{ textAlign: "right", padding: "0.75rem" }}>Short Game</th>
                <th style={{ textAlign: "right", padding: "0.75rem" }}>Putting</th>
              </tr>
            </thead>
            <tbody>
              {data.players.map((entry) => (
                <tr key={entry.player_name} style={{ borderBottom: "1px solid #e5e7eb" }}>
                  <td style={{ padding: "0.75rem", fontWeight: entry.player_name === selectedEntry.player_name ? 700 : 500 }}>
                    {entry.player_name}
                  </td>
                  <td style={{ padding: "0.75rem", textAlign: "right" }}>{entry.driving.toFixed(1)}</td>
                  <td style={{ padding: "0.75rem", textAlign: "right" }}>{entry.fairway.toFixed(1)}</td>
                  <td style={{ padding: "0.75rem", textAlign: "right" }}>{entry.short_game.toFixed(1)}</td>
                  <td style={{ padding: "0.75rem", textAlign: "right" }}>{entry.putting.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

function AccordionSection({
  title,
  description,
  isOpen,
  onToggle,
  children,
}: {
  title: string;
  description: string;
  isOpen: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: "0.85rem",
        backgroundColor: "#ffffff",
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        style={{
          width: "100%",
          textAlign: "left",
          background: "none",
          border: "none",
          padding: "1rem 1.25rem",
          cursor: "pointer",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem" }}>
          <div>
            <div style={{ fontSize: "1rem", fontWeight: 700, color: "#111827" }}>{title}</div>
            <div style={{ marginTop: "0.3rem", fontSize: "0.875rem", color: "#6b7280" }}>{description}</div>
          </div>
          <div style={{ fontSize: "1.2rem", color: "#6b7280", lineHeight: 1 }}>{isOpen ? "−" : "+"}</div>
        </div>
      </button>
      {isOpen && <div style={{ padding: "0 1.25rem 1.25rem" }}>{children}</div>}
    </section>
  );
}

export function AnalyticsPage() {
  const [expandedSections, setExpandedSections] = useState<Record<SectionId, boolean>>({
    "single-player": false,
    "performance-trends": false,
    "team-leaderboards": false,
    "hole-difficulty": false,
    "player-ratings": false,
  });

  const sectionContent: Record<SectionId, ReactNode> = useMemo(
    () => ({
      "single-player": <SinglePlayerLeaderboardsSection />,
      "performance-trends": <PerformanceTrendsSection />,
      "team-leaderboards": <TeamLeaderboardsSection />,
      "hole-difficulty": <HoleDifficultySection />,
      "player-ratings": <PlayerRatingsSection />,
    }),
    [],
  );

  return (
    <section style={{ maxWidth: 1120, margin: "0 auto", display: "grid", gap: "1rem" }}>
      <div>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "0.5rem" }}>Analytics</h1>
        <p style={{ margin: 0, color: "#4b5563" }}>
          Expand a section to view charts and leaderboards.
        </p>
      </div>

      {ANALYTICS_SECTIONS.map((section) => (
        <AccordionSection
          key={section.id}
          title={section.title}
          description={section.description}
          isOpen={expandedSections[section.id]}
          onToggle={() =>
            setExpandedSections((previous) => ({
              ...previous,
              [section.id]: !previous[section.id],
            }))
          }
        >
          {sectionContent[section.id]}
        </AccordionSection>
      ))}
    </section>
  );
}
