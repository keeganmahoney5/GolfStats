import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRound } from "../api/client";
import type { RoundDetail } from "../types/round";

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

function sumPar(arr: (number | null)[] | undefined, start: number, end: number): string {
  if (!arr) return "—";
  const vals = arr.slice(start, end).filter((v): v is number => v != null);
  if (vals.length === 0) return "—";
  return String(vals.reduce((a, b) => a + b, 0));
}

const sectionStyle = { maxWidth: 960, margin: "0 auto" as const };
const cardStyle = {
  padding: "1.5rem",
  borderRadius: "0.75rem",
  backgroundColor: "#ffffff",
  border: "1px solid #e5e7eb",
  marginBottom: "1rem",
};
const labelStyle = { display: "block", marginBottom: "0.25rem", fontWeight: 500, fontSize: "0.9rem", color: "#6b7280" };

export function RoundDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [round, setRound] = useState<RoundDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const rawId = id == null ? null : parseInt(id, 10);
    if (rawId == null || Number.isNaN(rawId)) {
      setError("Invalid round ID");
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getRound(rawId)
      .then((data) => {
        if (!cancelled) setRound(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load round");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <section style={sectionStyle}>
        <p style={{ color: "#6b7280" }}>Loading round…</p>
      </section>
    );
  }

  if (error || !round) {
    return (
      <section style={sectionStyle}>
        <p style={{ color: "#dc2626", marginBottom: "1rem" }}>{error ?? "Round not found"}</p>
        <Link to="/rounds" style={{ color: "#2563eb" }}>← Back to Rounds</Link>
      </section>
    );
  }

  return (
    <section style={sectionStyle}>
      <div style={{ marginBottom: "1rem", display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        <Link to="/rounds" style={{ color: "#2563eb", textDecoration: "none", fontSize: "0.95rem" }}>
          ← Back to Rounds
        </Link>
        {import.meta.env.VITE_USE_STATIC_DATA !== "true" && (
          <Link to={`/rounds/${round.id}/edit`} style={{ color: "#16a34a", textDecoration: "none", fontSize: "0.95rem", fontWeight: 500 }}>
            Edit round
          </Link>
        )}
      </div>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "0.75rem" }}>
        Round #{round.id}
      </h1>

      <div style={cardStyle}>
        <h2 style={{ fontSize: "1.15rem", fontWeight: 600, marginBottom: "1rem" }}>Round details</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "1rem" }}>
          <div>
            <span style={labelStyle}>Date</span>
            <div>{formatDate(round.date)}</div>
          </div>
          <div>
            <span style={labelStyle}>Course</span>
            <div>{round.course_name || "—"}</div>
          </div>
          <div>
            <span style={labelStyle}>Tee set</span>
            <div>{round.tee_set || "—"}</div>
          </div>
          <div>
            <span style={labelStyle}>Team round</span>
            <div>{round.is_team_round ? "Yes" : "No"}</div>
          </div>
        </div>
      </div>

      {((round.hole_pars ?? []).some((p) => p != null) || (round.stroke_indexes ?? []).some((s) => s != null)) && (
        <div style={cardStyle}>
          <h2 style={{ fontSize: "1.15rem", fontWeight: 600, marginBottom: "1rem" }}>Par &amp; Stroke Index</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(18, 1fr)", gap: "0.25rem", marginBottom: "0.5rem" }}>
            {Array.from({ length: 18 }, (_, i) => (
              <div key={i} style={{ textAlign: "center", fontSize: "0.8rem" }}>
                <div style={{ color: "#9ca3af", fontSize: "0.7rem" }}>{i + 1}</div>
                <div>{round.hole_pars?.[i] ?? "—"}</div>
                <div style={{ color: "#6b7280", fontSize: "0.7rem" }}>Par</div>
              </div>
            ))}
          </div>
          {(round.hole_pars ?? []).some((p) => p != null) && (
            <div style={{ fontSize: "0.85rem", color: "#6b7280", marginBottom: "0.75rem" }}>
              Front 9: {sumPar(round.hole_pars, 0, 9)} &nbsp;|&nbsp; Back 9: {sumPar(round.hole_pars, 9, 18)} &nbsp;|&nbsp; Total: {sumPar(round.hole_pars, 0, 18)}
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(18, 1fr)", gap: "0.25rem" }}>
            {Array.from({ length: 18 }, (_, i) => (
              <div key={i} style={{ textAlign: "center", fontSize: "0.8rem" }}>
                <div>{round.stroke_indexes?.[i] ?? "—"}</div>
                <div style={{ color: "#6b7280", fontSize: "0.7rem" }}>SI</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {round.players.map((player, pIdx) => (
        <div key={pIdx} style={cardStyle}>
          <h3 style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: "0.5rem" }}>
            {player.name}
            {player.team_name ? ` (${player.team_name})` : ""}
          </h3>

          <h4 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem", marginTop: "1rem" }}>Scores</h4>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(9, 1fr) auto", gap: "0.25rem 0.5rem", marginBottom: "0.5rem", alignItems: "stretch" }}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((holeNum) => {
              const hs = player.hole_scores.find((h) => h.hole_number === holeNum);
              return (
                <div
                  key={holeNum}
                  style={{
                    padding: "0.35rem",
                    textAlign: "center",
                    backgroundColor: "#f9fafb",
                    borderRadius: "0.25rem",
                    fontSize: "0.9rem",
                  }}
                >
                  <div style={{ fontSize: "0.7rem", color: "#6b7280" }}>{holeNum}</div>
                  <div>{hs?.score ?? "—"}</div>
                </div>
              );
            })}
            <div
              style={{
                padding: "0.35rem",
                textAlign: "center",
                backgroundColor: "#fef3c7",
                borderRadius: "0.25rem",
                fontSize: "0.9rem",
              }}
            >
              <div style={{ fontSize: "0.7rem", color: "#6b7280" }}>Out</div>
              <div>{player.stats.out_score ?? "—"}</div>
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(9, 1fr) auto", gap: "0.25rem 0.5rem", marginBottom: "0.75rem", alignItems: "stretch" }}>
            {[10, 11, 12, 13, 14, 15, 16, 17, 18].map((holeNum) => {
              const hs = player.hole_scores.find((h) => h.hole_number === holeNum);
              return (
                <div
                  key={holeNum}
                  style={{
                    padding: "0.35rem",
                    textAlign: "center",
                    backgroundColor: "#f9fafb",
                    borderRadius: "0.25rem",
                    fontSize: "0.9rem",
                  }}
                >
                  <div style={{ fontSize: "0.7rem", color: "#6b7280" }}>{holeNum}</div>
                  <div>{hs?.score ?? "—"}</div>
                </div>
              );
            })}
            <div
              style={{
                padding: "0.35rem",
                textAlign: "center",
                backgroundColor: "#fed7aa",
                borderRadius: "0.25rem",
                fontSize: "0.9rem",
              }}
            >
              <div style={{ fontSize: "0.7rem", color: "#6b7280" }}>In</div>
              <div>{player.stats.in_score ?? "—"}</div>
            </div>
          </div>
          <div
            style={{
              display: "inline-block",
              padding: "0.35rem 0.75rem",
              backgroundColor: "#e0e7ff",
              borderRadius: "0.25rem",
              fontSize: "0.9rem",
              marginBottom: "1rem",
            }}
          >
            <span style={{ fontSize: "0.75rem", color: "#6b7280", marginRight: "0.5rem" }}>Total</span>
            <strong>{player.stats.total_score ?? "—"}</strong>
          </div>

          {(player.stats.total_score != null ||
            player.stats.out_score != null ||
            player.stats.in_score != null ||
            player.stats.fairways_hit != null ||
            player.stats.gir != null ||
            player.stats.avg_drive_distance != null ||
            player.stats.total_putts != null) && (
            <>
              <h4 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem", marginTop: "0.5rem" }}>Stats</h4>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "0.5rem" }}>
                {player.stats.out_score != null && (
                  <div>
                    <span style={labelStyle}>Out</span>
                    <div>{player.stats.out_score}</div>
                  </div>
                )}
                {player.stats.in_score != null && (
                  <div>
                    <span style={labelStyle}>In</span>
                    <div>{player.stats.in_score}</div>
                  </div>
                )}
                {player.stats.total_score != null && (
                  <div>
                    <span style={labelStyle}>Total score</span>
                    <div>{player.stats.total_score}</div>
                  </div>
                )}
                {(player.stats.fairways_hit != null || player.stats.fairways_possible != null) && (
                  <div>
                    <span style={labelStyle}>Fairways</span>
                    <div>
                      {player.stats.fairways_hit ?? "—"} / {player.stats.fairways_possible ?? "—"}
                    </div>
                  </div>
                )}
                {(player.stats.gir != null || player.stats.gir_possible != null) && (
                  <div>
                    <span style={labelStyle}>GIR</span>
                    <div>
                      {player.stats.gir ?? "—"} / {player.stats.gir_possible ?? "—"}
                    </div>
                  </div>
                )}
                {player.stats.avg_drive_distance != null && (
                  <div>
                    <span style={labelStyle}>Avg drive (yd)</span>
                    <div>{player.stats.avg_drive_distance}</div>
                  </div>
                )}
                {player.stats.total_putts != null && (
                  <div>
                    <span style={labelStyle}>Total putts</span>
                    <div>{player.stats.total_putts}</div>
                  </div>
                )}
                {(player.stats.scramble_successes != null || player.stats.scramble_opportunities != null) && (
                  <div>
                    <span style={labelStyle}>Scramble</span>
                    <div>
                      {player.stats.scramble_successes ?? "—"} / {player.stats.scramble_opportunities ?? "—"}
                    </div>
                  </div>
                )}
                {(player.stats.sand_save_successes != null || player.stats.sand_save_opportunities != null) && (
                  <div>
                    <span style={labelStyle}>Sand save</span>
                    <div>
                      {player.stats.sand_save_successes ?? "—"} / {player.stats.sand_save_opportunities ?? "—"}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      ))}
    </section>
  );
}
