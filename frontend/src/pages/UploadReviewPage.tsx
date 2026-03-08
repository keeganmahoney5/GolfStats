import { useState } from "react";
import { Link } from "react-router-dom";
import exifr from "exifr";
import { ocrDraftRound, saveRound } from "../api/client";
import type { DraftRound, GridMapping, PlayerDraft, SaveRoundPayload, ScorecardGrid } from "../types/round";
import { ScorecardGridMapper } from "../components/ScorecardGridMapper";
import { ImageWarpEditor } from "../components/ImageWarpEditor";

/** Read capture date from image EXIF; returns YYYY-MM-DD or null. */
async function readExifDate(file: File): Promise<string | null> {
  try {
    const out = await exifr.parse(file, { pick: ["DateTimeOriginal", "CreateDate"] });
    const raw = out?.DateTimeOriginal ?? out?.CreateDate ?? null;
    if (raw instanceof Date) return raw.toISOString().slice(0, 10);
    if (typeof raw === "string") {
      const datePart = raw.trim().split(/\s+/)[0]?.replace(/:/g, "-") ?? "";
      return datePart.length >= 10 ? datePart.slice(0, 10) : null;
    }
    return null;
  } catch {
    return null;
  }
}

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

/** Merge a partial draft (from one grid) into the full draft by player name and hole index. */
function mergePartialDraftInto(
  full: DraftRound,
  partial: DraftRound,
): DraftRound {
  const norm = (s: string) => s.trim().toLowerCase();
  const fullNames = new Set(full.players.map((p) => norm(p.name)));
  const holeParList = full.hole_pars ?? [];
  const strokeIdxList = full.stroke_indexes ?? [];
  const hole_pars: (number | null)[] = Array.from({ length: 18 }, (_, h) => holeParList[h] ?? null);
  const stroke_indexes: (number | null)[] = Array.from({ length: 18 }, (_, h) => strokeIdxList[h] ?? null);
  const partialPars = partial.hole_pars ?? [];
  const partialSI = partial.stroke_indexes ?? [];
  for (let h = 0; h < 18; h++) {
    if (partialPars[h] != null) hole_pars[h] = partialPars[h];
    if (partialSI[h] != null) stroke_indexes[h] = partialSI[h];
  }
  const players = full.players.map((p) => {
    const match = partial.players.find((q) => norm(q.name) === norm(p.name));
    if (!match) return p;
    const holeScores = p.hole_scores.map((hs) => {
      const fromPartial = match.hole_scores.find((h) => h.hole_number === hs.hole_number);
      return fromPartial?.score != null ? { ...hs, score: fromPartial.score } : hs;
    });
    const stats = { ...p.stats };
    if (match.stats.total_score != null) stats.total_score = match.stats.total_score;
    if (match.stats.out_score != null) stats.out_score = match.stats.out_score;
    if (match.stats.in_score != null) stats.in_score = match.stats.in_score;
    return { ...p, hole_scores: holeScores, stats };
  });
  for (const partialPlayer of partial.players) {
    if (!fullNames.has(norm(partialPlayer.name))) {
      players.push(partialPlayer);
      fullNames.add(norm(partialPlayer.name));
    }
  }
  return {
    ...full,
    players,
    hole_pars,
    stroke_indexes,
  };
}

interface ScorecardSlot {
  file: File | null;
  blob: Blob | null;
  thumb: string | null;
  editing: boolean;
  inputKey: number;
}

function emptySlot(): ScorecardSlot {
  return { file: null, blob: null, thumb: null, editing: false, inputKey: 0 };
}

export function UploadReviewPage() {
  const [scorecards, setScorecards] = useState<ScorecardSlot[]>([emptySlot()]);

  const [statsFile, setStatsFile] = useState<File | null>(null);
  const [statsBlob, setStatsBlob] = useState<Blob | null>(null);
  const [statsThumb, setStatsThumb] = useState<string | null>(null);
  const [statsEditing, setStatsEditing] = useState(false);
  const [statsInputKey, setStatsInputKey] = useState(0);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftRound | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<number | null>(null);
  const [scorecardGrid, setScorecardGrid] = useState<ScorecardGrid | null>(null);
  const [predictedMapping, setPredictedMapping] = useState<GridMapping | null>(null);
  const [appliedMapping, setAppliedMapping] = useState<GridMapping | null>(null);
  const [scorecardGrids, setScorecardGrids] = useState<(ScorecardGrid | null)[] | null>(null);
  const [predictedMappings, setPredictedMappings] = useState<(GridMapping | null)[] | null>(null);
  const [selectedGridIndex, setSelectedGridIndex] = useState(0);
  const [appliedMappingsByIndex, setAppliedMappingsByIndex] = useState<Record<number, GridMapping>>({});
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [predictionWarnings, setPredictionWarnings] = useState<Record<string, string>>({});
  const [referenceImageTab, setReferenceImageTab] = useState<"scorecard-1" | "scorecard-2" | "stats">("scorecard-1");
  const [referenceCollapsed, setReferenceCollapsed] = useState(false);

  function updateSlot(idx: number, patch: Partial<ScorecardSlot>) {
    setScorecards((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  }

  function removeSlot(idx: number) {
    setScorecards((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      return next.length === 0 ? [emptySlot()] : next;
    });
  }

  const confirmedScorecards = scorecards.filter((s) => s.blob != null);
  const anyEditing = scorecards.some((s) => s.editing);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (confirmedScorecards.length === 0 && !statsBlob) {
      setError("Please confirm at least one image before running OCR.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const scFiles: File[] = [];
      for (const slot of scorecards) {
        if (slot.blob && slot.file) {
          scFiles.push(new File([slot.blob], slot.file.name, { type: "image/jpeg" }));
        }
      }
      const stFile = statsBlob && statsFile
        ? new File([statsBlob], statsFile.name, { type: "image/jpeg" })
        : null;
      let imageDateHint: string | null = null;
      for (const slot of scorecards) {
        if (slot.file && !imageDateHint) {
          imageDateHint = await readExifDate(slot.file);
        }
      }
      if (!imageDateHint && statsFile) imageDateHint = await readExifDate(statsFile);
      const result = await ocrDraftRound(scFiles, stFile, imageDateHint);
      setDraft(result);
      setScorecardGrid(result.scorecard_grid ?? null);
      setPredictedMapping(result.predicted_mapping ?? null);
      setScorecardGrids(result.scorecard_grids ?? null);
      setPredictedMappings(result.predicted_mappings ?? null);
      setAppliedMapping(null);
      setAppliedMappingsByIndex({});
      setSelectedGridIndex(0);
      setPredictionWarnings(result.prediction_meta?.field_warnings ?? {});
      setShowAdvanced(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  function updateRound<K extends keyof DraftRound>(key: K, value: DraftRound[K]) {
    if (!draft) return;
    setDraft({ ...draft, [key]: value });
  }

  function updatePlayer(index: number, updater: (p: PlayerDraft) => PlayerDraft) {
    if (!draft) return;
    const next = [...draft.players];
    next[index] = updater(next[index]);
    setDraft({ ...draft, players: next });
  }

  function removePlayer(index: number) {
    if (!draft || draft.players.length <= 1) return;
    const next = draft.players.filter((_, i) => i !== index);
    setDraft({ ...draft, players: next });
  }

  function addPlayer() {
    if (!draft) return;
    const next = [...draft.players, emptyPlayerDraft()];
    setDraft({ ...draft, players: next });
  }

  function buildSavePayload(): SaveRoundPayload {
    if (!draft) throw new Error("No draft");
    const holeParList = draft.hole_pars ?? [];
    const strokeIdxList = draft.stroke_indexes ?? [];
    const hole_pars = [...holeParList];
    const stroke_indexes = [...strokeIdxList];
    while (hole_pars.length < 18) hole_pars.push(null);
    while (stroke_indexes.length < 18) stroke_indexes.push(null);
    return {
      date: draft.date,
      course_name: draft.course_name,
      tee_set: draft.tee_set,
      is_team_round: draft.is_team_round,
      players: draft.players,
      hole_pars: hole_pars.slice(0, 18),
      stroke_indexes: stroke_indexes.slice(0, 18),
    };
  }

  async function handleSave() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const payload = buildSavePayload();
      const { id } = await saveRound(payload);
      setSaveSuccess(id);
      setDraft(null);
      setScorecards([emptySlot()]);
      setStatsFile(null);
      setScorecardGrid(null);
      setPredictedMapping(null);
      setScorecardGrids(null);
      setPredictedMappings(null);
      setAppliedMapping(null);
      setAppliedMappingsByIndex({});
      setSelectedGridIndex(0);
      setPredictionWarnings({});
      setShowAdvanced(false);
      setReferenceImageTab("scorecard-1");
      setReferenceCollapsed(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function handleDiscard() {
    setDraft(null);
    setScorecards([emptySlot()]);
    setStatsFile(null);
    setStatsBlob(null);
    setStatsThumb(null);
    setStatsEditing(false);
    setStatsInputKey((k) => k + 1);
    setError(null);
    setSaveSuccess(null);
    setScorecardGrid(null);
    setPredictedMapping(null);
    setScorecardGrids(null);
    setPredictedMappings(null);
    setAppliedMapping(null);
    setAppliedMappingsByIndex({});
    setSelectedGridIndex(0);
    setPredictionWarnings({});
    setShowAdvanced(false);
    setReferenceImageTab("scorecard-1");
    setReferenceCollapsed(false);
  }

  const sectionStyle = {
    maxWidth: 960,
    margin: "0 auto" as const,
  };
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

  return (
    <section style={sectionStyle}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "0.75rem" }}>
        Upload &amp; Review Round
      </h1>
      <p style={{ marginBottom: "1.5rem", color: "#4b5563" }}>
        Upload scorecard and stats screenshots. We&apos;ll OCR the data so you can review and edit before saving.
      </p>

      {saveSuccess !== null && (
        <div style={{ ...cardStyle, borderColor: "#22c55e", backgroundColor: "#f0fdf4", marginBottom: "1rem" }}>
          Round saved.{" "}
          <Link to={`/rounds/${saveSuccess}`} style={{ color: "#16a34a", fontWeight: 500 }}>View round</Link>
          {" or "}
          <Link to="/rounds" style={{ color: "#16a34a", fontWeight: 500 }}>see all rounds</Link>.
          You can add another round below.
        </div>
      )}

      {!draft ? (
        <div style={cardStyle}>
          <form onSubmit={handleUpload}>

            {/* Scorecard images */}
            <div style={{ marginBottom: "1rem" }}>
              <label style={labelStyle}>
                Scorecard image{scorecards.length > 1 ? "s" : ""}
              </label>
              <p style={{ fontSize: "0.8rem", color: "#6b7280", margin: "0 0 0.5rem" }}>
                Upload one image per 9 holes. Add a second image if your round covers front and back 9 on separate cards.
              </p>

              {scorecards.map((slot, idx) => (
                <div
                  key={idx}
                  style={{
                    marginBottom: "0.75rem",
                    paddingLeft: scorecards.length > 1 ? "0.75rem" : 0,
                    borderLeft: scorecards.length > 1 ? "3px solid #e5e7eb" : "none",
                  }}
                >
                  {scorecards.length > 1 && (
                    <div style={{ fontSize: "0.8rem", fontWeight: 600, color: "#374151", marginBottom: "0.25rem" }}>
                      Scorecard {idx + 1}
                    </div>
                  )}
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                    <input
                      key={slot.inputKey}
                      type="file"
                      accept="image/*"
                      onChange={(e) => {
                        const f = e.target.files?.[0] ?? null;
                        updateSlot(idx, { file: f, blob: null, thumb: null, editing: !!f });
                      }}
                      style={{ ...inputStyle, width: "auto" }}
                    />
                    {slot.thumb && !slot.editing && (
                      <>
                        <img
                          src={slot.thumb}
                          alt={`Scorecard ${idx + 1} cropped preview`}
                          style={{ height: 48, borderRadius: 4, border: "1px solid #d1d5db", objectFit: "cover" }}
                        />
                        <button
                          type="button"
                          onClick={() => updateSlot(idx, { editing: true })}
                          style={{
                            padding: "0.25rem 0.6rem",
                            fontSize: "0.8rem",
                            backgroundColor: "#f3f4f6",
                            border: "1px solid #d1d5db",
                            borderRadius: "0.4rem",
                            cursor: "pointer",
                            fontWeight: 500,
                          }}
                        >
                          Re-edit
                        </button>
                        <button
                          type="button"
                          onClick={() => removeSlot(idx)}
                          style={{
                            padding: "0.25rem 0.6rem",
                            fontSize: "0.8rem",
                            backgroundColor: "#fef2f2",
                            border: "1px solid #fecaca",
                            borderRadius: "0.4rem",
                            cursor: "pointer",
                            fontWeight: 500,
                            color: "#b91c1c",
                          }}
                        >
                          Remove
                        </button>
                        <span style={{ fontSize: "0.8rem", color: "#16a34a", fontWeight: 500 }}>✓ Confirmed</span>
                      </>
                    )}
                  </div>
                  {slot.file && slot.editing && (
                    <ImageWarpEditor
                      file={slot.file}
                      onConfirm={(blob) => {
                        const url = URL.createObjectURL(blob);
                        updateSlot(idx, { blob, thumb: url, editing: false });
                      }}
                      onCancel={() => {
                        if (!slot.blob) {
                          updateSlot(idx, { file: null, editing: false });
                        } else {
                          updateSlot(idx, { editing: false });
                        }
                      }}
                    />
                  )}
                </div>
              ))}

              <button
                type="button"
                onClick={() => setScorecards((prev) => [...prev, emptySlot()])}
                style={{
                  padding: "0.35rem 0.75rem",
                  fontSize: "0.85rem",
                  backgroundColor: "#f0fdf4",
                  border: "1px solid #bbf7d0",
                  borderRadius: "0.4rem",
                  cursor: "pointer",
                  fontWeight: 500,
                  color: "#15803d",
                }}
              >
                + Add another scorecard image
              </button>
            </div>

            {/* Stats image row */}
            <div style={{ marginBottom: "1rem" }}>
              <label style={labelStyle}>Stats image (optional)</label>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <input
                  key={statsInputKey}
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    setStatsFile(f);
                    setStatsBlob(null);
                    setStatsThumb(null);
                    setStatsEditing(!!f);
                  }}
                  style={{ ...inputStyle, width: "auto" }}
                />
                {statsThumb && !statsEditing && (
                  <>
                    <img
                      src={statsThumb}
                      alt="Stats cropped preview"
                      style={{ height: 48, borderRadius: 4, border: "1px solid #d1d5db", objectFit: "cover" }}
                    />
                    <button
                      type="button"
                      onClick={() => setStatsEditing(true)}
                      style={{
                        padding: "0.25rem 0.6rem",
                        fontSize: "0.8rem",
                        backgroundColor: "#f3f4f6",
                        border: "1px solid #d1d5db",
                        borderRadius: "0.4rem",
                        cursor: "pointer",
                        fontWeight: 500,
                      }}
                    >
                      Re-edit
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setStatsFile(null);
                        setStatsBlob(null);
                        setStatsThumb(null);
                        setStatsEditing(false);
                        setStatsInputKey((k) => k + 1);
                      }}
                      style={{
                        padding: "0.25rem 0.6rem",
                        fontSize: "0.8rem",
                        backgroundColor: "#fef2f2",
                        border: "1px solid #fecaca",
                        borderRadius: "0.4rem",
                        cursor: "pointer",
                        fontWeight: 500,
                        color: "#b91c1c",
                      }}
                    >
                      Remove
                    </button>
                    <span style={{ fontSize: "0.8rem", color: "#16a34a", fontWeight: 500 }}>✓ Confirmed</span>
                  </>
                )}
              </div>
              {statsFile && statsEditing && (
                <ImageWarpEditor
                  file={statsFile}
                  onConfirm={(blob) => {
                    const url = URL.createObjectURL(blob);
                    setStatsBlob(blob);
                    setStatsThumb(url);
                    setStatsEditing(false);
                  }}
                  onCancel={() => {
                    if (!statsBlob) {
                      setStatsFile(null);
                    }
                    setStatsEditing(false);
                  }}
                />
              )}
            </div>

            {/* Hint when files are selected but not yet confirmed */}
            {(anyEditing || statsEditing) && (
              <p style={{ fontSize: "0.85rem", color: "#6b7280", marginBottom: "0.75rem" }}>
                Confirm the image(s) above before running OCR.
              </p>
            )}

            {error && (
              <p style={{ color: "#dc2626", marginBottom: "0.75rem", fontSize: "0.9rem" }}>{error}</p>
            )}

            {(() => {
              const allScorecardsDone = scorecards.every((s) => !s.file || !!s.blob);
              const hasConfirmed = confirmedScorecards.length > 0 || !!statsBlob;
              const canOcr = allScorecardsDone && (!statsFile || !!statsBlob) && hasConfirmed;
              return (
                <button
                  type="submit"
                  disabled={loading || !canOcr}
                  title={!canOcr ? "Confirm at least one image first" : undefined}
                  style={{
                    padding: "0.5rem 1rem",
                    backgroundColor: loading ? "#9ca3af" : canOcr ? "#2563eb" : "#93c5fd",
                    color: "#fff",
                    border: "none",
                    borderRadius: "0.5rem",
                    fontWeight: 500,
                    cursor: loading || !canOcr ? "not-allowed" : "pointer",
                  }}
                >
                  {loading ? "Running OCR…" : "Upload & run OCR"}
                </button>
              );
            })()}
          </form>
        </div>
      ) : (
        <>
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
              {saving ? "Saving…" : "Save round"}
            </button>
            <button
              type="button"
              onClick={handleDiscard}
              disabled={saving}
              style={{
                padding: "0.5rem 1rem",
                backgroundColor: "#6b7280",
                color: "#fff",
                border: "none",
                borderRadius: "0.5rem",
                fontWeight: 500,
                cursor: saving ? "not-allowed" : "pointer",
              }}
            >
              Discard
            </button>
            {error && (
              <span style={{ color: "#dc2626", fontSize: "0.9rem" }}>{error}</span>
            )}
            {(scorecardGrid || (scorecardGrids?.length ?? 0) > 0) && (
              <button
                type="button"
                onClick={() => setShowAdvanced((v) => !v)}
                style={{
                  padding: "0.5rem 1rem",
                  backgroundColor: showAdvanced ? "#7c3aed" : "#f5f3ff",
                  color: showAdvanced ? "#fff" : "#6d28d9",
                  border: "1px solid #c4b5fd",
                  borderRadius: "0.5rem",
                  fontWeight: 500,
                  cursor: "pointer",
                }}
              >
                {showAdvanced ? "Hide grid mapper" : "Adjust mapping"}
              </button>
            )}
          </div>

          {(() => {
            const refTabs: { id: "scorecard-1" | "scorecard-2" | "stats"; label: string; url: string }[] = [];
            scorecards.forEach((slot, idx) => {
              if (slot.thumb) {
                refTabs.push({
                  id: idx === 0 ? "scorecard-1" : "scorecard-2",
                  label: scorecards.filter((s) => s.thumb).length > 1 ? `Scorecard ${idx + 1}` : "Scorecard",
                  url: slot.thumb,
                });
              }
            });
            if (statsThumb) {
              refTabs.push({ id: "stats", label: "Stats", url: statsThumb });
            }
            if (refTabs.length === 0) return null;
            const activeTab = refTabs.find((t) => t.id === referenceImageTab) ?? refTabs[0];
            return (
              <div style={{ ...cardStyle, marginBottom: "1rem" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: referenceCollapsed ? 0 : "0.75rem",
                  }}
                >
                  <div>
                    <span style={{ fontSize: "1rem", fontWeight: 600 }}>Reference images</span>
                    <span style={{ fontSize: "0.82rem", color: "#6b7280", marginLeft: "0.6rem" }}>
                      View cropped images while editing below
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setReferenceCollapsed((v) => !v)}
                    style={{
                      padding: "0.2rem 0.5rem",
                      fontSize: "0.8rem",
                      backgroundColor: "#f3f4f6",
                      border: "1px solid #d1d5db",
                      borderRadius: "0.375rem",
                      cursor: "pointer",
                      fontWeight: 500,
                      color: "#374151",
                    }}
                  >
                    {referenceCollapsed ? "Show" : "Hide"}
                  </button>
                </div>
                {!referenceCollapsed && (
                  <>
                    {refTabs.length > 1 && (
                      <div style={{ display: "flex", gap: "0.25rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
                        {refTabs.map((tab) => (
                          <button
                            key={tab.id}
                            type="button"
                            onClick={() => setReferenceImageTab(tab.id)}
                            style={{
                              padding: "0.3rem 0.7rem",
                              fontSize: "0.85rem",
                              fontWeight: 500,
                              border: "1px solid #d1d5db",
                              borderRadius: "0.375rem",
                              backgroundColor: activeTab.id === tab.id ? "#1e40af" : "#f9fafb",
                              color: activeTab.id === tab.id ? "#fff" : "#374151",
                              cursor: "pointer",
                            }}
                          >
                            {tab.label}
                          </button>
                        ))}
                      </div>
                    )}
                    <div
                      style={{
                        border: "1px solid #e5e7eb",
                        borderRadius: "0.5rem",
                        overflow: "hidden",
                        backgroundColor: "#f9fafb",
                        textAlign: "center",
                      }}
                    >
                      <img
                        src={activeTab.url}
                        alt={activeTab.label}
                        style={{
                          maxWidth: "100%",
                          maxHeight: "60vh",
                          objectFit: "contain",
                          display: "block",
                          margin: "0 auto",
                        }}
                      />
                    </div>
                  </>
                )}
              </div>
            );
          })()}

          {Object.keys(predictionWarnings).length > 0 && !showAdvanced && (
            <div style={{
              ...cardStyle,
              borderColor: "#facc15",
              backgroundColor: "#fefce8",
              fontSize: "0.9rem",
              color: "#854d0e",
            }}>
              Some fields could not be confidently extracted and were left blank.
              You can edit them below or{" "}
              <button
                type="button"
                onClick={() => setShowAdvanced(true)}
                style={{
                  background: "none",
                  border: "none",
                  color: "#6d28d9",
                  fontWeight: 600,
                  cursor: "pointer",
                  padding: 0,
                  fontSize: "inherit",
                  textDecoration: "underline",
                }}
              >
                adjust the mapping
              </button>{" "}
              to fix them.
            </div>
          )}

          {showAdvanced && (() => {
            const grids = scorecardGrids ?? (scorecardGrid != null ? [scorecardGrid] : []);
            const mappings = predictedMappings ?? (predictedMapping != null ? [predictedMapping] : []);
            const currentGrid = grids[selectedGridIndex] ?? null;
            const currentMapping = appliedMappingsByIndex[selectedGridIndex] ?? mappings[selectedGridIndex] ?? appliedMapping ?? predictedMapping ?? null;
            const hasMultipleGrids = grids.length > 1;

            if (grids.length === 0) return null;

            return (
              <div style={cardStyle}>
                {hasMultipleGrids && (
                  <div style={{ display: "flex", gap: "0.25rem", marginBottom: "1rem", flexWrap: "wrap" }}>
                    {grids.map((g, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => setSelectedGridIndex(idx)}
                        style={{
                          padding: "0.4rem 0.75rem",
                          fontSize: "0.9rem",
                          fontWeight: 500,
                          border: "1px solid #c4b5fd",
                          borderRadius: "0.375rem",
                          backgroundColor: selectedGridIndex === idx ? "#7c3aed" : "#f5f3ff",
                          color: selectedGridIndex === idx ? "#fff" : "#6d28d9",
                          cursor: "pointer",
                        }}
                      >
                        Scorecard {idx + 1}
                      </button>
                    ))}
                  </div>
                )}
                {currentGrid != null && (
                  <ScorecardGridMapper
                    grid={currentGrid}
                    initialMapping={currentMapping}
                    onApply={(mapped, mapping) => {
                      setAppliedMapping(mapping);
                      setAppliedMappingsByIndex((prev) => ({ ...prev, [selectedGridIndex]: mapping }));
                      if (!draft) return;
                      if (hasMultipleGrids) {
                        const merged = mergePartialDraftInto(draft, mapped);
                        setDraft({
                          ...merged,
                          scorecard_grid: draft.scorecard_grid,
                          scorecard_grids: draft.scorecard_grids,
                          predicted_mapping: draft.predicted_mapping,
                          predicted_mappings: draft.predicted_mappings,
                        });
                      } else {
                        setDraft({
                          ...mapped,
                          date: draft.date,
                          course_name: draft.course_name,
                          tee_set: draft.tee_set,
                          is_team_round: draft.is_team_round,
                          hole_pars: draft.hole_pars,
                          stroke_indexes: draft.stroke_indexes,
                          raw_scorecard_text: draft.raw_scorecard_text,
                          raw_stats_text: draft.raw_stats_text,
                          scorecard_grid: currentGrid,
                          scorecard_grids: draft.scorecard_grids,
                          predicted_mapping: draft.predicted_mapping,
                          predicted_mappings: draft.predicted_mappings,
                        });
                      }
                      setShowAdvanced(false);
                    }}
                  />
                )}
                {currentGrid == null && hasMultipleGrids && (
                  <p style={{ color: "#6b7280", fontSize: "0.9rem" }}>
                    No grid data for this image. You can still adjust the other scorecard(s) above.
                  </p>
                )}
              </div>
            );
          })()}

          <div style={cardStyle}>
            <h2 style={{ fontSize: "1.15rem", fontWeight: 600, marginBottom: "1rem" }}>Round details</h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
              <div>
                <label style={labelStyle}>Date</label>
                <input
                  type="date"
                  value={draft.date ?? ""}
                  onChange={(e) => updateRound("date", e.target.value || null)}
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Course name</label>
                <input
                  type="text"
                  value={draft.course_name ?? ""}
                  onChange={(e) => updateRound("course_name", e.target.value || null)}
                  placeholder="Course name"
                  style={inputStyle}
                />
              </div>
              <div>
                <label style={labelStyle}>Tee set</label>
                <input
                  type="text"
                  value={draft.tee_set ?? ""}
                  onChange={(e) => updateRound("tee_set", e.target.value || null)}
                  placeholder="e.g. Blue"
                  style={inputStyle}
                />
              </div>
              <div style={{ display: "flex", alignItems: "flex-end", gap: "0.5rem" }}>
                <label style={{ ...labelStyle, marginBottom: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <input
                    type="checkbox"
                    checked={draft.is_team_round}
                    onChange={(e) => updateRound("is_team_round", e.target.checked)}
                  />
                  Team round
                </label>
              </div>
            </div>

            <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.5rem", marginTop: "1rem", color: "#6b7280" }}>
              Optional: Par &amp; Stroke Index
            </h3>
            <p style={{ fontSize: "0.85rem", color: "#9ca3af", marginBottom: "0.75rem" }}>
              Par and stroke index per hole. Leave blank if unknown. Front 9 / Back 9 / Total par are shown when entered.
            </p>
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
                      value={(draft.hole_pars?.[i] ?? "") === "" ? "" : draft.hole_pars?.[i]}
                      onChange={(e) => {
                        const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                        const next = [...(draft.hole_pars ?? []), ...Array(18).fill(null)].slice(0, 18);
                        next[i] = v;
                        updateRound("hole_pars", next);
                      }}
                      style={{ ...inputStyle, padding: "0.35rem", textAlign: "center", fontSize: "0.85rem" }}
                    />
                  </div>
                ))}
              </div>
              {(draft.hole_pars ?? []).some((p) => p != null) && (
                <div style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: "0.35rem" }}>
                  Front 9: {sumPar(draft.hole_pars ?? [], 0, 9)} &nbsp;|&nbsp; Back 9: {sumPar(draft.hole_pars ?? [], 9, 18)} &nbsp;|&nbsp; Total: {sumPar(draft.hole_pars ?? [], 0, 18)}
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
                      value={(draft.stroke_indexes?.[i] ?? "") === "" ? "" : draft.stroke_indexes?.[i]}
                      onChange={(e) => {
                        const v = e.target.value === "" ? null : parseInt(e.target.value, 10);
                        const next = [...(draft.stroke_indexes ?? []), ...Array(18).fill(null)].slice(0, 18);
                        next[i] = v;
                        updateRound("stroke_indexes", next);
                      }}
                      style={{ ...inputStyle, padding: "0.35rem", textAlign: "center", fontSize: "0.85rem" }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>

          {draft.players.map((player, pIdx) => (
            <div key={pIdx} style={cardStyle}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem", flexWrap: "wrap", gap: "0.5rem" }}>
                <h3 style={{ fontSize: "1.05rem", fontWeight: 600, margin: 0 }}>
                  Player {pIdx + 1}
                </h3>
                {draft.players.length > 1 && (
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
                    title="Front 9 total (from scorecard)"
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
                    title="Back 9 total (from scorecard)"
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
        </>
      )}
    </section>
  );
}
