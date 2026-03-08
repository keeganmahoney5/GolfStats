import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getRound, updateRound } from "../api/client";
import type { RoundDetail, PlayerDraft, SaveRoundPayload } from "../types/round";

function sumPar(arr: (number | null)[], start: number, end: number): string {
  const vals = arr.slice(start, end).filter((v): v is number => v != null);
  if (vals.length === 0) return "—";
  return String(vals.reduce((a, b) => a + b, 0));
}

function emptyPlayerDraft(): PlayerDraft {
  return {
    name: "",
    team_name: null,
    hole_scores: Array.from({ length: 18 }, (_, i) => ({ hole_number: i + 1, score: null })),
    stats: {
      total_score: null,
      out_score: null,
      in_score: null,
      fairways_hit: null,
      fairways_possible: null,
      gir: null,
      gir_possible: null,
      avg_drive_distance: null,
      total_putts: null,
      scramble_successes: null,
      scramble_opportunities: null,
      sand_save_successes: null,
      sand_save_opportunities: null,
    },
  };
}

const sectionStyle = { maxWidth: 960, margin: "0 auto" as const };
const cardStyle = {
  padding: "1.5rem",
  borderRadius: "0.75rem",
  backgroundColor: "#ffffff",
  border: "1px solid #e5e7eb",
  marginBottom: "1rem",
};
const inputStyle = {
  padding: "0.5rem 0.75rem",
  border: "1px solid #d1d5db",
  borderRadius: "0.5rem",
  fontSize: "0.95rem",
  width: "100%",
  boxSizing: "border-box" as const,
};
const labelStyle = { display: "block", marginBottom: "0.25rem", fontWeight: 500, fontSize: "0.9rem" };

export function RoundEditPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [round, setRound] = useState<RoundDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
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

  function updateRoundField<K extends keyof RoundDetail>(key: K, value: RoundDetail[K]) {
    if (!round) return;
    setRound({ ...round, [key]: value });
  }

  function updatePlayer(index: number, updater: (p: PlayerDraft) => PlayerDraft) {
    if (!round) return;
    const next = [...round.players];
    next[index] = updater(next[index]);
    setRound({ ...round, players: next });
  }

  function removePlayer(index: number) {
    if (!round || round.players.length <= 1) return;
    const next = round.players.filter((_, i) => i !== index);
    setRound({ ...round, players: next });
  }

  function addPlayer() {
    if (!round) return;
    const next = [...round.players, emptyPlayerDraft()];
    setRound({ ...round, players: next });
  }

  function buildSavePayload(): SaveRoundPayload {
    if (!round) throw new Error("No round");
    const holeParList = round.hole_pars ?? [];
    const strokeIdxList = round.stroke_indexes ?? [];
    const hole_pars = [...holeParList];
    const stroke_indexes = [...strokeIdxList];
    while (hole_pars.length < 18) hole_pars.push(null);
    while (stroke_indexes.length < 18) stroke_indexes.push(null);
    return {
      date: round.date,
      course_name: round.course_name,
      tee_set: round.tee_set,
      is_team_round: round.is_team_round,
      players: round.players,
      hole_pars: hole_pars.slice(0, 18),
      stroke_indexes: stroke_indexes.slice(0, 18),
    };
  }

  async function handleSave() {
    if (!round) return;
    setSaving(true);
    setError(null);
    try {
      const payload = buildSavePayload();
      await updateRound(round.id, payload);
      navigate(`/rounds/${round.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSaving(false);
    }
  }

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
      <div style={{ marginBottom: "1rem", display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
        <Link to={`/rounds/${round.id}`} style={{ color: "#2563eb", textDecoration: "none", fontSize: "0.95rem" }}>
          ← Back to round
        </Link>
      </div>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "0.75rem" }}>
        Edit Round #{round.id}
      </h1>

      <div style={{ ...cardStyle, display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: "0.5rem 1rem",
            backgroundColor: saving ? "#9ca3af" : "#16a34a",
            color: "#fff",
            border: "none",
            borderRadius: "0.5rem",
            fontWeight: 500,
            cursor: saving ? "not-allowed" : "pointer",
          }}
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
        {error && (
          <span style={{ color: "#dc2626", fontSize: "0.9rem" }}>{error}</span>
        )}
      </div>

      <div style={cardStyle}>
        <h2 style={{ fontSize: "1.15rem", fontWeight: 600, marginBottom: "1rem" }}>Round details</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
          <div>
            <label style={labelStyle}>Date</label>
            <input
              type="date"
              value={round.date ?? ""}
              onChange={(e) => updateRoundField("date", e.target.value || null)}
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Course name</label>
            <input
              type="text"
              value={round.course_name ?? ""}
              onChange={(e) => updateRoundField("course_name", e.target.value || null)}
              placeholder="Course name"
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Tee set</label>
            <input
              type="text"
              value={round.tee_set ?? ""}
              onChange={(e) => updateRoundField("tee_set", e.target.value || null)}
              placeholder="e.g. Blue"
              style={inputStyle}
            />
          </div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: "0.5rem" }}>
            <label style={{ ...labelStyle, marginBottom: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <input
                type="checkbox"
                checked={round.is_team_round}
                onChange={(e) => updateRoundField("is_team_round", e.target.checked)}
              />
              Team round
            </label>
          </div>
        </div>

        <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.5rem", marginTop: "1rem", color: "#6b7280" }}>
          Optional: Par &amp; Stroke Index
        </h3>
        <div style={{ marginBottom: "0.5rem" }}>
          <div style={{ fontSize: "0.75rem", fontWeight: 500, color: "#6b7280", marginBottom: "0.25rem" }}>Par</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(18, 1fr)", gap: "0.2rem" }}>
            {Array.from({ length: 18 }, (_, i) => (
              <div key={i} style={{ minWidth: 0 }}>
                <label style={{ fontSize: "0.65rem", display: "block", color: "#9ca3af" }}>{i + 1}</label>
                <input
                  type="number"
                  min={3}
                  max={5}
                  value={(round.hole_pars?.[i] ?? "") === "" ? "" : round.hole_pars?.[i]}
                  onChange={(e) => {
                    const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                    const next = [...(round.hole_pars ?? []), ...Array(18).fill(null)].slice(0, 18);
                    next[i] = v;
                    updateRoundField("hole_pars", next);
                  }}
                  style={{ ...inputStyle, padding: "0.35rem", textAlign: "center", fontSize: "0.85rem" }}
                />
              </div>
            ))}
          </div>
          {(round.hole_pars ?? []).some((p) => p != null) && (
            <div style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: "0.35rem" }}>
              Front 9: {sumPar(round.hole_pars ?? [], 0, 9)} &nbsp;|&nbsp; Back 9: {sumPar(round.hole_pars ?? [], 9, 18)} &nbsp;|&nbsp; Total: {sumPar(round.hole_pars ?? [], 0, 18)}
            </div>
          )}
        </div>
        <div>
          <div style={{ fontSize: "0.75rem", fontWeight: 500, color: "#6b7280", marginBottom: "0.25rem" }}>Stroke Index</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(18, 1fr)", gap: "0.2rem" }}>
            {Array.from({ length: 18 }, (_, i) => (
              <div key={i} style={{ minWidth: 0 }}>
                <label style={{ fontSize: "0.65rem", display: "block", color: "#9ca3af" }}>{i + 1}</label>
                <input
                  type="number"
                  min={1}
                  max={18}
                  value={(round.stroke_indexes?.[i] ?? "") === "" ? "" : round.stroke_indexes?.[i]}
                  onChange={(e) => {
                    const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                    const next = [...(round.stroke_indexes ?? []), ...Array(18).fill(null)].slice(0, 18);
                    next[i] = v;
                    updateRoundField("stroke_indexes", next);
                  }}
                  style={{ ...inputStyle, padding: "0.35rem", textAlign: "center", fontSize: "0.85rem" }}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      {round.players.map((player, pIdx) => (
        <div key={pIdx} style={cardStyle}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 600, margin: 0 }}>Player {pIdx + 1}</h3>
            {round.players.length > 1 && (
              <button
                type="button"
                onClick={() => removePlayer(pIdx)}
                style={{
                  padding: "0.35rem 0.75rem",
                  backgroundColor: "#fef2f2",
                  color: "#b91c1c",
                  border: "1px solid #fecaca",
                  borderRadius: "0.5rem",
                  fontSize: "0.85rem",
                  fontWeight: 500,
                  cursor: "pointer",
                }}
              >
                Remove player
              </button>
            )}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <label style={labelStyle}>Name</label>
              <input
                type="text"
                value={player.name}
                onChange={(e) => updatePlayer(pIdx, (p) => ({ ...p, name: e.target.value }))}
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Team name (optional)</label>
              <input
                type="text"
                value={player.team_name ?? ""}
                onChange={(e) => updatePlayer(pIdx, (p) => ({ ...p, team_name: e.target.value || null }))}
                style={inputStyle}
              />
            </div>
          </div>

          <h4 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem" }}>Scores</h4>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(9, 1fr) auto", gap: "0.25rem 0.5rem", alignItems: "end", marginBottom: "0.5rem" }}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((holeNum) => {
              const hs = player.hole_scores.find((h) => h.hole_number === holeNum);
              return (
                <div key={holeNum}>
                  <label style={{ ...labelStyle, fontSize: "0.75rem" }}>{holeNum}</label>
                  <input
                    type="number"
                    min={1}
                    max={15}
                    value={hs?.score ?? ""}
                    onChange={(e) => {
                      const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                      updatePlayer(pIdx, (p) => {
                        const next = [...p.hole_scores];
                        const i = next.findIndex((h) => h.hole_number === holeNum);
                        if (i >= 0) next[i] = { ...next[i], score: v ?? null };
                        else next.push({ hole_number: holeNum, score: v ?? null });
                        next.sort((a, b) => a.hole_number - b.hole_number);
                        return { ...p, hole_scores: next };
                      });
                    }}
                    style={{ ...inputStyle, padding: "0.35rem", textAlign: "center" }}
                  />
                </div>
              );
            })}
            <div>
              <label style={{ ...labelStyle, fontSize: "0.75rem" }}>Out</label>
              <input
                type="number"
                min={0}
                value={player.stats.out_score ?? ""}
                onChange={(e) => {
                  const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                  updatePlayer(pIdx, (p) => ({ ...p, stats: { ...p.stats, out_score: v } }));
                }}
                style={{ ...inputStyle, padding: "0.35rem", textAlign: "center" }}
                title="Front 9 total"
              />
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(9, 1fr) auto", gap: "0.25rem 0.5rem", alignItems: "end", marginBottom: "0.5rem" }}>
            {[10, 11, 12, 13, 14, 15, 16, 17, 18].map((holeNum) => {
              const hs = player.hole_scores.find((h) => h.hole_number === holeNum);
              return (
                <div key={holeNum}>
                  <label style={{ ...labelStyle, fontSize: "0.75rem" }}>{holeNum}</label>
                  <input
                    type="number"
                    min={1}
                    max={15}
                    value={hs?.score ?? ""}
                    onChange={(e) => {
                      const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                      updatePlayer(pIdx, (p) => {
                        const next = [...p.hole_scores];
                        const i = next.findIndex((h) => h.hole_number === holeNum);
                        if (i >= 0) next[i] = { ...next[i], score: v ?? null };
                        else next.push({ hole_number: holeNum, score: v ?? null });
                        next.sort((a, b) => a.hole_number - b.hole_number);
                        return { ...p, hole_scores: next };
                      });
                    }}
                    style={{ ...inputStyle, padding: "0.35rem", textAlign: "center" }}
                  />
                </div>
              );
            })}
            <div>
              <label style={{ ...labelStyle, fontSize: "0.75rem" }}>In</label>
              <input
                type="number"
                min={0}
                value={player.stats.in_score ?? ""}
                onChange={(e) => {
                  const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                  updatePlayer(pIdx, (p) => ({ ...p, stats: { ...p.stats, in_score: v } }));
                }}
                style={{ ...inputStyle, padding: "0.35rem", textAlign: "center" }}
                title="Back 9 total"
              />
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "0.5rem", maxWidth: 120, marginBottom: "1rem" }}>
            <div>
              <label style={{ ...labelStyle, fontSize: "0.75rem" }}>Total</label>
              <input
                type="number"
                min={0}
                value={player.stats.total_score ?? ""}
                onChange={(e) => {
                  const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                  updatePlayer(pIdx, (p) => ({ ...p, stats: { ...p.stats, total_score: v } }));
                }}
                style={{ ...inputStyle, padding: "0.35rem", textAlign: "center" }}
              />
            </div>
          </div>

          <h4 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem" }}>Stats</h4>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "0.5rem" }}>
            {([
              {
                label: "Fairways %",
                hit: "fairways_hit",
                possible: "fairways_possible",
              },
              {
                label: "GIR %",
                hit: "gir",
                possible: "gir_possible",
              },
              {
                label: "Scramble %",
                hit: "scramble_successes",
                possible: "scramble_opportunities",
              },
              {
                label: "Sand save %",
                hit: "sand_save_successes",
                possible: "sand_save_opportunities",
              },
            ] as const).map(({ label, hit, possible }) => {
              const h = (player.stats as Record<string, number | null>)[hit];
              const p = (player.stats as Record<string, number | null>)[possible];
              const displayValue = h != null && p != null && p > 0 ? Math.round((h / p) * 100) : "";
              return (
                <div key={hit}>
                  <label style={{ ...labelStyle, fontSize: "0.8rem" }}>{label}</label>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={displayValue}
                    onChange={(e) => {
                      const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                      const clamped = v != null ? Math.max(0, Math.min(100, v)) : null;
                      updatePlayer(pIdx, (p) => ({
                        ...p,
                        stats: {
                          ...p.stats,
                          [hit]: clamped,
                          [possible]: clamped != null ? 100 : null,
                        },
                      }));
                    }}
                    style={{ ...inputStyle, padding: "0.35rem" }}
                    placeholder="0–100"
                  />
                </div>
              );
            })}
            {([
              ["avg_drive_distance", "Avg drive (yd)"],
              ["total_putts", "Total putts"],
            ] as const).map(([key, label]) => (
              <div key={key}>
                <label style={{ ...labelStyle, fontSize: "0.8rem" }}>{label}</label>
                <input
                  type="number"
                  min={0}
                  value={(player.stats as Record<string, number | null>)[key] ?? ""}
                  onChange={(e) => {
                    const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                    updatePlayer(pIdx, (p) => ({ ...p, stats: { ...p.stats, [key]: v } }));
                  }}
                  style={{ ...inputStyle, padding: "0.35rem" }}
                />
              </div>
            ))}
          </div>
        </div>
      ))}
      <div style={{ ...cardStyle, borderStyle: "dashed", borderWidth: 2 }}>
        <button
          type="button"
          onClick={addPlayer}
          style={{
            width: "100%",
            padding: "0.75rem 1rem",
            backgroundColor: "#f9fafb",
            color: "#6b7280",
            border: "1px solid #e5e7eb",
            borderRadius: "0.5rem",
            fontSize: "0.9rem",
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          + Add player
        </button>
      </div>
    </section>
  );
}
