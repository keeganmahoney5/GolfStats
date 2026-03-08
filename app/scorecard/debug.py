"""Debug overlay and serialisable debug structures for v2 parse."""
from __future__ import annotations

import io
from typing import List, Optional

import cv2
import numpy as np

from .models import (
    CellRepair,
    CellValue,
    DebugLayout,
    GridGeometry,
    OcrToken,
    ValidationResult,
)


def build_debug_payload(
    geometry: Optional[GridGeometry],
    tokens: List[OcrToken],
    validation: Optional[ValidationResult],
    cell_values: List[List[CellValue]],
) -> DebugLayout:
    """Build a JSON-safe debug payload."""
    repaired: List[dict] = []
    if validation:
        for r in validation.repairs:
            repaired.append({
                "row": r.row,
                "col": r.col,
                "old": r.old_value,
                "new": r.new_value,
                "reason": r.reason,
            })

    cell_confs: List[dict] = []
    for row in cell_values:
        for cv in row:
            cell_confs.append({
                "row": cv.row,
                "col": cv.col,
                "text": cv.best_text,
                "confidence": round(cv.confidence, 3),
            })

    return DebugLayout(
        strategy_used=geometry.strategy if geometry else "none",
        strategy_confidence=round(geometry.strategy_confidence, 3) if geometry else 0.0,
        col_boundaries=geometry.col_boundaries if geometry else [],
        row_boundaries=geometry.row_boundaries if geometry else [],
        n_tokens=len(tokens),
        n_rows=geometry.n_rows if geometry else 0,
        n_cols=geometry.n_cols if geometry else 0,
        panel_detected=geometry is not None and geometry.strategy != "empty",
        repaired_cells=repaired,
        cell_confidences=cell_confs,
    )


def render_debug_overlay(
    image_bytes: bytes,
    geometry: Optional[GridGeometry],
    tokens: List[OcrToken],
    cell_values: List[List[CellValue]],
) -> Optional[bytes]:
    """Draw grid lines and token boxes on the image and return JPEG bytes."""
    buf = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        return None

    h, w = img.shape[:2]

    if geometry:
        for x in geometry.col_boundaries:
            xi = int(x)
            cv2.line(img, (xi, 0), (xi, h), (0, 255, 0), 1)
        for y in geometry.row_boundaries:
            yi = int(y)
            cv2.line(img, (0, yi), (w, yi), (0, 255, 0), 1)

    for t in tokens:
        x1, y1 = int(t.min_x), int(t.min_y)
        x2, y2 = int(t.max_x), int(t.max_y)
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 0), 1)
        cv2.putText(img, t.text, (x1, max(y1 - 2, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255), 1)

    ok, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return None
    return bytes(encoded)
