import { useState, useMemo } from "react";
import type { ScorecardGrid, GridMapping, DraftRound } from "../types/round";
import { mapGridToDraft } from "../api/client";

interface Props {
  grid: ScorecardGrid;
  initialMapping?: GridMapping | null;
  onApply: (draft: DraftRound, mapping: GridMapping) => void;
}

type SelectionMode = "header" | "name" | "holes" | "total" | "out" | "in" | "playerStart" | "playerEnd" | "parRow" | "strokeIndexRow";

const MODE_LABELS: Record<SelectionMode, string> = {
  header: "Header row",
  name: "Name column",
  holes: "Hole columns",
  total: "Total column",
  out: "Out column",
  in: "In column",
  playerStart: "First player row",
  playerEnd: "Last player row",
  parRow: "Par row",
  strokeIndexRow: "Stroke index row",
};

const MODE_COLORS: Record<SelectionMode, string> = {
  header: "#e5e7eb",
  name: "#dbeafe",
  holes: "#dcfce7",
  total: "#fef3c7",
  out: "#fde68a",
  in: "#fed7aa",
  playerStart: "#ede9fe",
  playerEnd: "#fce7f3",
  parRow: "#d1fae5",
  strokeIndexRow: "#e0e7ff",
};

export function ScorecardGridMapper({ grid, initialMapping, onApply }: Props) {
  const [headerRow, setHeaderRow] = useState<number | null>(initialMapping?.header_row ?? null);
  const [nameCol, setNameCol] = useState<number>(initialMapping?.name_col ?? 0);
  const [holeCols, setHoleCols] = useState<number[]>(initialMapping?.hole_cols ?? []);
  const [totalCol, setTotalCol] = useState<number | null>(initialMapping?.total_col ?? null);
  const [outCol, setOutCol] = useState<number | null>(initialMapping?.out_col ?? null);
  const [inCol, setInCol] = useState<number | null>(initialMapping?.in_col ?? null);
  const [firstPlayerRow, setFirstPlayerRow] = useState<number>(initialMapping?.first_player_row ?? 0);
  const [lastPlayerRow, setLastPlayerRow] = useState<number | null>(initialMapping?.last_player_row ?? null);
  const [parRow, setParRow] = useState<number | null>(initialMapping?.par_row ?? null);
  const [strokeIndexRow, setStrokeIndexRow] = useState<number | null>(initialMapping?.stroke_index_row ?? null);
  const [firstHoleNumber] = useState<number>(initialMapping?.first_hole_number ?? 1);
  const [mode, setMode] = useState<SelectionMode>("name");
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const maxCols = useMemo(
    () => Math.max(...grid.rows.map((r) => r.length), 0),
    [grid]
  );

  function handleColClick(colIdx: number) {
    if (mode === "name") {
      setNameCol(colIdx);
    } else if (mode === "holes") {
      setHoleCols((prev) =>
        prev.includes(colIdx)
          ? prev.filter((c) => c !== colIdx)
          : [...prev, colIdx].sort((a, b) => a - b)
      );
    } else if (mode === "total") {
      setTotalCol((prev) => (prev === colIdx ? null : colIdx));
    } else if (mode === "out") {
      setOutCol((prev) => (prev === colIdx ? null : colIdx));
    } else if (mode === "in") {
      setInCol((prev) => (prev === colIdx ? null : colIdx));
    }
  }

  function handleRowClick(rowIdx: number) {
    if (mode === "header") {
      setHeaderRow((prev) => (prev === rowIdx ? null : rowIdx));
    } else if (mode === "playerStart") {
      setFirstPlayerRow(rowIdx);
    } else if (mode === "playerEnd") {
      setLastPlayerRow((prev) => (prev === rowIdx ? null : rowIdx));
    } else if (mode === "parRow") {
      setParRow((prev) => (prev === rowIdx ? null : rowIdx));
    } else if (mode === "strokeIndexRow") {
      setStrokeIndexRow((prev) => (prev === rowIdx ? null : rowIdx));
    }
  }

  function cellBg(rowIdx: number, colIdx: number): string | undefined {
    if (headerRow !== null && rowIdx === headerRow) return MODE_COLORS.header;
    if (parRow !== null && rowIdx === parRow && holeCols.includes(colIdx)) return MODE_COLORS.parRow;
    if (strokeIndexRow !== null && rowIdx === strokeIndexRow && holeCols.includes(colIdx)) return MODE_COLORS.strokeIndexRow;
    if (colIdx === nameCol) return MODE_COLORS.name;
    if (holeCols.includes(colIdx)) return MODE_COLORS.holes;
    if (totalCol !== null && colIdx === totalCol) return MODE_COLORS.total;
    if (outCol !== null && colIdx === outCol) return MODE_COLORS.out;
    if (inCol !== null && colIdx === inCol) return MODE_COLORS.in;
    return undefined;
  }

  function rowGutterBg(rowIdx: number): string | undefined {
    if (headerRow !== null && rowIdx === headerRow) return MODE_COLORS.header;
    if (rowIdx === firstPlayerRow) return MODE_COLORS.playerStart;
    if (lastPlayerRow !== null && rowIdx === lastPlayerRow) return MODE_COLORS.playerEnd;
    if (parRow !== null && rowIdx === parRow) return MODE_COLORS.parRow;
    if (strokeIndexRow !== null && rowIdx === strokeIndexRow) return MODE_COLORS.strokeIndexRow;
    return undefined;
  }

  function colHeaderBg(colIdx: number): string | undefined {
    if (colIdx === nameCol) return MODE_COLORS.name;
    if (holeCols.includes(colIdx)) return MODE_COLORS.holes;
    if (totalCol !== null && colIdx === totalCol) return MODE_COLORS.total;
    if (outCol !== null && colIdx === outCol) return MODE_COLORS.out;
    if (inCol !== null && colIdx === inCol) return MODE_COLORS.in;
    return undefined;
  }

  async function handleApply() {
    if (holeCols.length === 0) {
      setError("Select at least one hole column.");
      return;
    }
    setApplying(true);
    setError(null);
    try {
      const mapping: GridMapping = {
        header_row: headerRow,
        name_col: nameCol,
        hole_cols: holeCols,
        total_col: totalCol,
        out_col: outCol,
        in_col: inCol,
        first_player_row: firstPlayerRow,
        last_player_row: lastPlayerRow,
        first_hole_number: firstHoleNumber,
        par_row: parRow,
        stroke_index_row: strokeIndexRow,
      };
      const draft = await mapGridToDraft(grid, mapping);
      onApply(draft, mapping);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mapping failed");
    } finally {
      setApplying(false);
    }
  }

  const previewPlayers = useMemo(() => {
    const last = lastPlayerRow ?? grid.rows.length - 1;
    const names: string[] = [];
    for (let r = firstPlayerRow; r <= last && r < grid.rows.length; r++) {
      if (r === headerRow) continue;
      const row = grid.rows[r];
      const name = row[nameCol] ?? "";
      if (name.trim()) names.push(name);
    }
    return names;
  }, [grid, firstPlayerRow, lastPlayerRow, headerRow, nameCol]);

  const btnBase: React.CSSProperties = {
    padding: "0.4rem 0.75rem",
    border: "1px solid #d1d5db",
    borderRadius: "0.375rem",
    fontSize: "0.85rem",
    fontWeight: 500,
    cursor: "pointer",
    backgroundColor: "#fff",
  };

  return (
    <div>
      <h3
        style={{
          fontSize: "1.05rem",
          fontWeight: 600,
          marginBottom: "0.5rem",
        }}
      >
        Advanced: Grid Mapping
      </h3>
      <p
        style={{
          fontSize: "0.875rem",
          color: "#6b7280",
          marginBottom: "1rem",
        }}
      >
        Adjust the auto-detected mapping if needed. Select a mode below,
        then click column headers or row labels to reassign them.
      </p>

      {/* Mode selector */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.5rem",
          marginBottom: "1rem",
        }}
      >
        {(Object.keys(MODE_LABELS) as SelectionMode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            style={{
              ...btnBase,
              backgroundColor: mode === m ? MODE_COLORS[m] : "#fff",
              borderColor: mode === m ? "#2563eb" : "#d1d5db",
            }}
          >
            {MODE_LABELS[m]}
          </button>
        ))}
      </div>

      <p style={{ fontSize: "0.8rem", color: "#6b7280", marginBottom: "0.75rem" }}>
        Mode:{" "}
        <strong>
          {MODE_LABELS[mode]}
        </strong>
        {(mode === "header" || mode === "playerStart" || mode === "playerEnd" || mode === "parRow" || mode === "strokeIndexRow")
          ? " — click a row label (R#) on the left."
          : " — click a column header (Col#) at the top."}
        {mode === "out" && " Out = front 9 total from scorecard."}
        {mode === "in" && " In = back 9 total from scorecard."}
      </p>

      {/* Legend */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.75rem",
          fontSize: "0.8rem",
          marginBottom: "0.75rem",
        }}
      >
        {([
          ["Name col", MODE_COLORS.name],
          ["Hole cols", MODE_COLORS.holes],
          ["Total col", MODE_COLORS.total],
          ["Out col", MODE_COLORS.out],
          ["In col", MODE_COLORS.in],
          ["Header row", MODE_COLORS.header],
          ["1st player row", MODE_COLORS.playerStart],
          ["Last player row", MODE_COLORS.playerEnd],
          ["Par row", MODE_COLORS.parRow],
          ["Stroke index row", MODE_COLORS.strokeIndexRow],
        ] as const).map(([label, color]) => (
          <span key={label} style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
            <span
              style={{
                display: "inline-block",
                width: 14,
                height: 14,
                borderRadius: 2,
                backgroundColor: color,
                border: "1px solid #d1d5db",
              }}
            />
            {label}
          </span>
        ))}
      </div>

      {/* Grid table */}
      <div
        style={{
          overflowX: "auto",
          border: "1px solid #e5e7eb",
          borderRadius: "0.5rem",
          marginBottom: "1rem",
        }}
      >
        <table
          style={{
            borderCollapse: "collapse",
            fontSize: "0.8rem",
            minWidth: "100%",
          }}
        >
          <thead>
            <tr>
              <th
                style={{
                  padding: "0.35rem 0.5rem",
                  borderBottom: "1px solid #e5e7eb",
                  backgroundColor: "#f9fafb",
                  position: "sticky",
                  left: 0,
                  zIndex: 1,
                }}
              />
              {Array.from({ length: maxCols }, (_, ci) => (
                <th
                  key={ci}
                  onClick={() => handleColClick(ci)}
                  style={{
                    padding: "0.35rem 0.5rem",
                    borderBottom: "1px solid #e5e7eb",
                    cursor:
                      mode === "name" || mode === "holes" || mode === "total" || mode === "out" || mode === "in"
                        ? "pointer"
                        : "default",
                    backgroundColor: colHeaderBg(ci) ?? "#f9fafb",
                    whiteSpace: "nowrap",
                    userSelect: "none",
                  }}
                >
                  Col {ci}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.rows.map((row, ri) => (
              <tr key={ri}>
                <td
                  onClick={() => handleRowClick(ri)}
                  style={{
                    padding: "0.35rem 0.5rem",
                    fontWeight: 600,
                    borderRight: "1px solid #e5e7eb",
                    borderBottom: "1px solid #f3f4f6",
                    cursor:
                      mode === "header" ||
                      mode === "playerStart" ||
                      mode === "playerEnd" ||
                      mode === "parRow" ||
                      mode === "strokeIndexRow"
                        ? "pointer"
                        : "default",
                    backgroundColor: rowGutterBg(ri) ?? "#f9fafb",
                    position: "sticky",
                    left: 0,
                    zIndex: 1,
                    whiteSpace: "nowrap",
                    userSelect: "none",
                  }}
                >
                  R{ri}
                </td>
                {Array.from({ length: maxCols }, (_, ci) => (
                  <td
                    key={ci}
                    style={{
                      padding: "0.35rem 0.5rem",
                      borderBottom: "1px solid #f3f4f6",
                      backgroundColor: cellBg(ri, ci),
                      whiteSpace: "nowrap",
                    }}
                  >
                    {row[ci] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Current selections summary */}
      <div
        style={{
          fontSize: "0.85rem",
          marginBottom: "1rem",
          padding: "0.75rem",
          backgroundColor: "#f9fafb",
          borderRadius: "0.5rem",
          border: "1px solid #e5e7eb",
        }}
      >
        <div style={{ marginBottom: "0.25rem" }}>
          <strong>Header row:</strong> {headerRow !== null ? `R${headerRow}` : "none"}
        </div>
        <div style={{ marginBottom: "0.25rem" }}>
          <strong>Name column:</strong> Col {nameCol}
        </div>
        <div style={{ marginBottom: "0.25rem" }}>
          <strong>Hole columns ({holeCols.length}):</strong>{" "}
          {holeCols.length > 0
            ? holeCols.map((c) => `Col ${c}`).join(", ")
            : "none selected"}
        </div>
        <div style={{ marginBottom: "0.25rem" }}>
          <strong>Total column:</strong>{" "}
          {totalCol !== null ? `Col ${totalCol}` : "none"}
        </div>
        <div style={{ marginBottom: "0.25rem" }}>
          <strong>Out column:</strong>{" "}
          {outCol !== null ? `Col ${outCol}` : "none"}
        </div>
        <div style={{ marginBottom: "0.25rem" }}>
          <strong>In column:</strong>{" "}
          {inCol !== null ? `Col ${inCol}` : "none"}
        </div>
        <div style={{ marginBottom: "0.25rem" }}>
          <strong>Player rows:</strong> R{firstPlayerRow}
          {lastPlayerRow !== null ? ` – R${lastPlayerRow}` : " – end"}
        </div>
        <div style={{ marginBottom: "0.25rem" }}>
          <strong>Par row:</strong> {parRow !== null ? `R${parRow}` : "none (optional)"}
        </div>
        <div style={{ marginBottom: "0.25rem" }}>
          <strong>Stroke index row:</strong> {strokeIndexRow !== null ? `R${strokeIndexRow}` : "none (optional)"}
        </div>
        <div>
          <strong>Players detected ({previewPlayers.length}):</strong>{" "}
          {previewPlayers.length > 0 ? previewPlayers.join(", ") : "none"}
        </div>
      </div>

      {error && (
        <p style={{ color: "#dc2626", fontSize: "0.9rem", marginBottom: "0.75rem" }}>
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={handleApply}
        disabled={applying}
        style={{
          padding: "0.5rem 1rem",
          backgroundColor: applying ? "#9ca3af" : "#2563eb",
          color: "#fff",
          border: "none",
          borderRadius: "0.5rem",
          fontWeight: 500,
          cursor: applying ? "not-allowed" : "pointer",
        }}
      >
        {applying ? "Applying…" : "Apply mapping"}
      </button>
    </div>
  );
}
