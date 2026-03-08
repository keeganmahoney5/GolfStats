import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getRounds, deleteRound } from "../api/client";
import type { RoundSummary } from "../types/round";

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

function TabButton<T extends string>({
  value,
  current,
  onChange,
  label,
}: {
  value: T;
  current: T;
  onChange: (v: T) => void;
  label: string;
}) {
  const active = value === current;
  return (
    <button
      type="button"
      onClick={() => onChange(value)}
      style={{
        padding: "0.4rem 0.75rem",
        borderRadius: "0.5rem",
        border: `1px solid ${active ? "#2563eb" : "#e5e7eb"}`,
        background: active ? "#eff6ff" : "#ffffff",
        color: active ? "#2563eb" : "#6b7280",
        fontWeight: active ? 600 : 400,
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
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
      <TabButton value={9} current={value} onChange={onChange} label="9 Holes" />
      <TabButton value={18} current={value} onChange={onChange} label="18 Holes" />
    </div>
  );
}

export function RoundsPage() {
  const [rounds, setRounds] = useState<RoundSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [tab, setTab] = useState<"singles" | "teams">("singles");
  const [holesMode, setHolesMode] = useState<9 | 18>(18);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getRounds()
      .then((data) => {
        if (!cancelled) setRounds(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load rounds");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const isTeamRound = tab === "teams";
  const filteredRounds = useMemo(
    () =>
      rounds.filter(
        (r) => r.is_team_round === isTeamRound && r.holes_type === holesMode
      ),
    [rounds, isTeamRound, holesMode]
  );

  const isStaticMode = import.meta.env.VITE_USE_STATIC_DATA === "true";
  const emptyMessage =
    tab === "singles"
      ? "No singles rounds yet."
      : "No team rounds yet.";

  if (loading) {
    return (
      <section style={{ maxWidth: 960, margin: "0 auto" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "0.75rem" }}>
          Rounds
        </h1>
        <p style={{ color: "#6b7280" }}>Loading rounds…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section style={{ maxWidth: 960, margin: "0 auto" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "0.75rem" }}>
          Rounds
        </h1>
        <p style={{ color: "#dc2626", marginBottom: "1rem" }}>{error}</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          style={{
            padding: "0.5rem 1rem",
            backgroundColor: "#2563eb",
            color: "#fff",
            border: "none",
            borderRadius: "0.375rem",
            cursor: "pointer",
          }}
        >
          Retry
        </button>
      </section>
    );
  }

  return (
    <section style={{ maxWidth: 960, margin: "0 auto" }}>
      <h1 style={{ fontSize: "1.5rem", fontWeight: 600, marginBottom: "0.75rem" }}>
        Rounds
      </h1>
      <p style={{ marginBottom: "1rem", color: "#4b5563" }}>
        Your saved rounds. Click a row to view the full scorecard.
      </p>
      <div style={{ display: "flex", gap: "0.25rem", marginBottom: "1rem" }}>
        <TabButton value="singles" current={tab} onChange={setTab} label="Singles" />
        <TabButton value="teams" current={tab} onChange={setTab} label="Teams" />
      </div>
      <HolesToggle value={holesMode} onChange={setHolesMode} />
      <div
        style={{
          borderRadius: "0.75rem",
          backgroundColor: "#ffffff",
          border: "1px solid #e5e7eb",
          overflow: "hidden",
        }}
      >
        {filteredRounds.length === 0 ? (
          <div style={{ padding: "2rem", textAlign: "center", color: "#6b7280" }}>
            {emptyMessage}
            {!isStaticMode && (
              <>
                {" "}
                <Link to="/" style={{ color: "#2563eb" }}>
                  Upload a scorecard
                </Link>{" "}
                to get started.
              </>
            )}
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ backgroundColor: "#f9fafb", borderBottom: "1px solid #e5e7eb" }}>
                <th style={{ padding: "0.75rem 1rem", textAlign: "left", fontWeight: 600, fontSize: "0.875rem" }}>
                  Date
                </th>
                <th style={{ padding: "0.75rem 1rem", textAlign: "left", fontWeight: 600, fontSize: "0.875rem" }}>
                  Course
                </th>
                <th style={{ padding: "0.75rem 1rem", textAlign: "left", fontWeight: 600, fontSize: "0.875rem" }}>
                  Players
                </th>
                <th style={{ padding: "0.75rem 1rem", textAlign: "right", fontWeight: 600, fontSize: "0.875rem" }}>
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredRounds.map((r) => (
                <tr
                  key={r.id}
                  style={{
                    borderBottom: "1px solid #e5e7eb",
                  }}
                >
                  <td style={{ padding: "0.75rem 1rem" }}>{formatDate(r.date)}</td>
                  <td style={{ padding: "0.75rem 1rem" }}>
                    {r.course_name || "—"}
                    {r.tee_set ? ` (${r.tee_set})` : ""}
                  </td>
                  <td style={{ padding: "0.75rem 1rem" }}>
                    {r.player_names.length ? r.player_names.join(", ") : "—"}
                  </td>
                  <td style={{ padding: "0.75rem 1rem", textAlign: "right" }}>
                    <span style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", flexWrap: "wrap" }}>
                      <Link
                        to={`/rounds/${r.id}`}
                        style={{
                          color: "#2563eb",
                          textDecoration: "none",
                          fontWeight: 500,
                        }}
                      >
                        View
                      </Link>
                      {!isStaticMode && (
                        <>
                          <Link
                            to={`/rounds/${r.id}/edit`}
                            style={{
                              color: "#16a34a",
                              textDecoration: "none",
                              fontWeight: 500,
                            }}
                          >
                            Edit
                          </Link>
                          <button
                            type="button"
                            disabled={deletingId === r.id}
                            onClick={() => {
                              if (!window.confirm(`Delete this round (${r.course_name || "Round"} from ${formatDate(r.date)})? This cannot be undone.`)) return;
                              setDeletingId(r.id);
                              deleteRound(r.id)
                                .then(() => {
                                  setRounds((prev) => prev.filter((x) => x.id !== r.id));
                                })
                                .catch((err) => {
                                  setError(err instanceof Error ? err.message : "Delete failed");
                                })
                                .finally(() => setDeletingId(null));
                            }}
                            style={{
                              padding: "0.25rem 0.5rem",
                              fontSize: "0.85rem",
                              color: "#b91c1c",
                              backgroundColor: "transparent",
                              border: "1px solid #fecaca",
                              borderRadius: "0.375rem",
                              cursor: deletingId === r.id ? "not-allowed" : "pointer",
                              fontWeight: 500,
                            }}
                          >
                            {deletingId === r.id ? "Deleting…" : "Delete"}
                          </button>
                        </>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
