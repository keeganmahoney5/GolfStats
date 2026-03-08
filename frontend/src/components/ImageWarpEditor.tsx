import { useCallback, useEffect, useRef, useState } from "react";
import { detectCorners, warpImage, type CornerPoint } from "../api/client";

const HANDLE_RADIUS = 10;
const COLORS = ["#ef4444", "#3b82f6", "#22c55e", "#f59e0b"];
const LABELS = ["TL", "TR", "BR", "BL"];

interface ImageWarpEditorProps {
  file: File;
  onConfirm: (blob: Blob) => void;
  onCancel: () => void;
}

export function ImageWarpEditor({ file, onConfirm, onCancel }: ImageWarpEditorProps) {
  const [imageSrc, setImageSrc] = useState<string>("");
  const [corners, setCorners] = useState<CornerPoint[]>([]);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [warping, setWarping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    setImageSrc(url);
    setCorners([]);
    setNaturalSize(null);
    setError(null);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function defaultCorners(w: number, h: number): CornerPoint[] {
    const inset = 0.05;
    return [
      { x: w * inset, y: h * inset },
      { x: w * (1 - inset), y: h * inset },
      { x: w * (1 - inset), y: h * (1 - inset) },
      { x: w * inset, y: h * (1 - inset) },
    ];
  }

  function orderForDisplay(pts: CornerPoint[]): CornerPoint[] {
    const arr = [...pts];
    const cx = arr.reduce((s, p) => s + p.x, 0) / 4;
    const cy = arr.reduce((s, p) => s + p.y, 0) / 4;
    arr.sort((a, b) => Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx));
    const sums = arr.map((p) => p.x + p.y);
    const tlIdx = sums.indexOf(Math.min(...sums));
    const ordered: CornerPoint[] = [];
    for (let i = 0; i < 4; i++) ordered.push(arr[(tlIdx + i) % 4]);
    return ordered;
  }

  async function runAutoDetect(w: number, h: number) {
    setDetecting(true);
    setError(null);
    try {
      const result = await detectCorners(file);
      setCorners(orderForDisplay(result.corners));
    } catch {
      setCorners(defaultCorners(w, h));
    } finally {
      setDetecting(false);
    }
  }

  function handleImageLoad(e: React.SyntheticEvent<HTMLImageElement>) {
    const img = e.currentTarget;
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    setNaturalSize({ w, h });
    setCorners(defaultCorners(w, h));
    runAutoDetect(w, h);
  }

  function handleReset() {
    if (naturalSize) setCorners(defaultCorners(naturalSize.w, naturalSize.h));
  }

  async function handleConfirm() {
    if (corners.length !== 4) return;
    setWarping(true);
    setError(null);
    try {
      const blob = await warpImage(file, corners);
      onConfirm(blob);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Warp failed");
    } finally {
      setWarping(false);
    }
  }

  // --- Canvas rendering ---

  const getScale = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !naturalSize) return { sx: 1, sy: 1 };
    return { sx: canvas.width / naturalSize.w, sy: canvas.height / naturalSize.h };
  }, [naturalSize]);

  const drawOverlay = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !naturalSize) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const { sx, sy } = getScale();
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (corners.length === 4) {
      ctx.beginPath();
      ctx.moveTo(corners[0].x * sx, corners[0].y * sy);
      for (let i = 1; i < 4; i++) ctx.lineTo(corners[i].x * sx, corners[i].y * sy);
      ctx.closePath();
      ctx.strokeStyle = "rgba(37, 99, 235, 0.85)";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = "rgba(37, 99, 235, 0.07)";
      ctx.fill();
    }

    corners.forEach((pt, i) => {
      const cx = pt.x * sx;
      const cy = pt.y * sy;
      ctx.beginPath();
      ctx.arc(cx, cy, HANDLE_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = COLORS[i];
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = "#fff";
      ctx.font = "bold 10px system-ui";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(LABELS[i], cx, cy);
    });
  }, [corners, naturalSize, getScale]);

  useEffect(() => { drawOverlay(); }, [drawOverlay]);

  // Sync canvas pixel size with displayed image size
  useEffect(() => {
    function syncSize() {
      const container = containerRef.current;
      const canvas = canvasRef.current;
      if (!container || !canvas || !naturalSize) return;
      const img = container.querySelector("img");
      if (!img) return;
      canvas.width = img.clientWidth;
      canvas.height = img.clientHeight;
      drawOverlay();
    }
    syncSize();
    window.addEventListener("resize", syncSize);
    return () => window.removeEventListener("resize", syncSize);
  }, [naturalSize, drawOverlay]);

  // --- Pointer events ---

  function toNatural(clientX: number, clientY: number): CornerPoint | null {
    const canvas = canvasRef.current;
    if (!canvas || !naturalSize) return null;
    const rect = canvas.getBoundingClientRect();
    const { sx, sy } = getScale();
    return { x: (clientX - rect.left) / sx, y: (clientY - rect.top) / sy };
  }

  function findHandle(clientX: number, clientY: number): number | null {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const px = clientX - rect.left;
    const py = clientY - rect.top;
    const { sx, sy } = getScale();
    for (let i = 0; i < corners.length; i++) {
      const dist = Math.hypot(corners[i].x * sx - px, corners[i].y * sy - py);
      if (dist <= HANDLE_RADIUS + 6) return i;
    }
    return null;
  }

  function findClosestCorner(pt: CornerPoint): number {
    let best = 0;
    let bestDist = Math.hypot(corners[0].x - pt.x, corners[0].y - pt.y);
    for (let i = 1; i < corners.length; i++) {
      const d = Math.hypot(corners[i].x - pt.x, corners[i].y - pt.y);
      if (d < bestDist) { bestDist = d; best = i; }
    }
    return best;
  }

  function handlePointerDown(e: React.PointerEvent) {
    const idx = findHandle(e.clientX, e.clientY);
    if (idx !== null) {
      setDragging(idx);
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      return;
    }
    const pt = toNatural(e.clientX, e.clientY);
    if (!pt || !naturalSize || corners.length !== 4) return;
    const clamped = {
      x: Math.max(0, Math.min(naturalSize.w, pt.x)),
      y: Math.max(0, Math.min(naturalSize.h, pt.y)),
    };
    const closest = findClosestCorner(pt);
    setCorners((prev) => prev.map((c, i) => (i === closest ? clamped : c)));
  }

  function handlePointerMove(e: React.PointerEvent) {
    if (dragging === null) return;
    const pt = toNatural(e.clientX, e.clientY);
    if (!pt || !naturalSize) return;
    const clamped = {
      x: Math.max(0, Math.min(naturalSize.w, pt.x)),
      y: Math.max(0, Math.min(naturalSize.h, pt.y)),
    };
    setCorners((prev) => prev.map((c, i) => (i === dragging ? clamped : c)));
  }

  const btnBase: React.CSSProperties = {
    padding: "0.45rem 0.9rem",
    border: "none",
    borderRadius: "0.5rem",
    fontWeight: 500,
    fontSize: "0.9rem",
    cursor: "pointer",
  };

  return (
    <div style={{
      marginTop: "0.75rem",
      border: "2px solid #2563eb",
      borderRadius: "0.75rem",
      padding: "1rem",
      backgroundColor: "#eff6ff",
    }}>
      <div style={{ marginBottom: "0.6rem", fontSize: "0.85rem", color: "#1e40af", fontWeight: 500 }}>
        {detecting
          ? "Detecting corners…"
          : "Adjust the 4 corner handles (drag or click to move), then confirm."}
      </div>

      <div
        ref={containerRef}
        style={{ position: "relative", display: "inline-block", maxWidth: "100%" }}
      >
        {imageSrc && (
          <img
            src={imageSrc}
            onLoad={handleImageLoad}
            alt="Scorecard preview"
            style={{
              display: "block",
              maxWidth: "100%",
              maxHeight: "55vh",
              height: "auto",
              objectFit: "contain",
            }}
            draggable={false}
          />
        )}
        <canvas
          ref={canvasRef}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={() => setDragging(null)}
          style={{
            position: "absolute",
            top: 0, left: 0,
            width: "100%", height: "100%",
            cursor: dragging !== null ? "grabbing" : "crosshair",
            touchAction: "none",
          }}
        />
      </div>

      {error && (
        <p style={{ color: "#dc2626", fontSize: "0.85rem", margin: "0.5rem 0 0" }}>{error}</p>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={handleConfirm}
          disabled={warping || corners.length !== 4}
          style={{
            ...btnBase,
            backgroundColor: warping ? "#9ca3af" : "#16a34a",
            color: "#fff",
            cursor: warping ? "not-allowed" : "pointer",
          }}
        >
          {warping ? "Correcting…" : "Confirm & Crop"}
        </button>
        <button
          type="button"
          onClick={handleReset}
          style={{ ...btnBase, backgroundColor: "#e5e7eb", color: "#374151" }}
        >
          Reset corners
        </button>
        <button
          type="button"
          onClick={onCancel}
          style={{ ...btnBase, backgroundColor: "transparent", color: "#6b7280", border: "1px solid #d1d5db" }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
