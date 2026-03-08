"""Grid reconstruction: detect table rows/columns from image lines or OCR boxes.

Two strategies are implemented and the one with higher confidence wins:
1. **Line-based** -- adaptive threshold, morphological enhancement,
   HoughLinesP, then cluster detected line positions into row/column
   separators.  Works well when the scorecard has visible grid lines.
2. **Text-box clustering** -- cluster OCR token centres on x/y axes to
   infer column/row boundaries.  Fallback when grid lines are faint or
   absent (e.g. dark backgrounds, low-contrast displays).
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .models import CellRect, GridGeometry, OcrToken


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cluster_1d(values: List[float], min_gap: float) -> List[float]:
    """Simple 1-D gap-based clustering, returns sorted cluster centres."""
    if not values:
        return []
    vals = sorted(values)
    clusters: List[List[float]] = [[vals[0]]]
    for v in vals[1:]:
        if v - (sum(clusters[-1]) / len(clusters[-1])) > min_gap:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return [sum(c) / len(c) for c in clusters]


def _boundaries_from_centres(centres: List[float], margin: float = 0.0) -> List[float]:
    """Convert N sorted cluster centres into N+1 boundary edges."""
    if not centres:
        return []
    boundaries: List[float] = []
    if margin > 0:
        boundaries.append(centres[0] - margin)
    else:
        boundaries.append(centres[0] - (centres[1] - centres[0]) / 2 if len(centres) > 1 else centres[0] - 20)
    for i in range(len(centres) - 1):
        boundaries.append((centres[i] + centres[i + 1]) / 2)
    if margin > 0:
        boundaries.append(centres[-1] + margin)
    else:
        boundaries.append(centres[-1] + (centres[-1] - centres[-2]) / 2 if len(centres) > 1 else centres[-1] + 20)
    return boundaries


def _make_cells(col_bounds: List[float], row_bounds: List[float]) -> List[CellRect]:
    cells: List[CellRect] = []
    for ri in range(len(row_bounds) - 1):
        for ci in range(len(col_bounds) - 1):
            cells.append(CellRect(
                row=ri, col=ci,
                x_min=col_bounds[ci], x_max=col_bounds[ci + 1],
                y_min=row_bounds[ri], y_max=row_bounds[ri + 1],
            ))
    return cells


# ---------------------------------------------------------------------------
# Strategy 1: line-based
# ---------------------------------------------------------------------------

def _detect_lines(gray: np.ndarray) -> Tuple[List[float], List[float], float]:
    """Detect horizontal/vertical line positions via morphology + Hough.

    Returns (vertical_positions, horizontal_positions, confidence).
    """
    h, w = gray.shape[:2]

    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 25, 12,
    )

    # Horizontal lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(w // 15, 20), 1))
    h_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=1)
    h_lines = cv2.HoughLinesP(h_mask, 1, np.pi / 180, threshold=50,
                               minLineLength=w // 6, maxLineGap=w // 20)

    # Vertical lines
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(h // 15, 20)))
    v_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=1)
    v_lines = cv2.HoughLinesP(v_mask, 1, np.pi / 180, threshold=50,
                               minLineLength=h // 6, maxLineGap=h // 20)

    vert_xs: List[float] = []
    horiz_ys: List[float] = []

    if v_lines is not None:
        for line in v_lines:
            x1, y1, x2, y2 = line[0]
            if abs(x2 - x1) < abs(y2 - y1) * 0.3:
                vert_xs.append((x1 + x2) / 2.0)

    if h_lines is not None:
        for line in h_lines:
            x1, y1, x2, y2 = line[0]
            if abs(y2 - y1) < abs(x2 - x1) * 0.3:
                horiz_ys.append((y1 + y2) / 2.0)

    min_gap_x = max(w * 0.02, 8)
    min_gap_y = max(h * 0.02, 8)

    vert_clusters = _cluster_1d(vert_xs, min_gap_x)
    horiz_clusters = _cluster_1d(horiz_ys, min_gap_y)

    n_vert = len(vert_clusters)
    n_horiz = len(horiz_clusters)

    if n_vert >= 3 and n_horiz >= 3:
        confidence = min(1.0, (n_vert * n_horiz) / 60.0)
    elif n_vert >= 2 or n_horiz >= 2:
        confidence = 0.3
    else:
        confidence = 0.0

    return vert_clusters, horiz_clusters, confidence


def line_based_reconstruction(
    image_bytes: bytes,
) -> Optional[GridGeometry]:
    """Attempt grid reconstruction using detected lines."""
    buf = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    vert_pos, horiz_pos, confidence = _detect_lines(gray)

    if confidence < 0.1 or len(vert_pos) < 3 or len(horiz_pos) < 3:
        return None

    col_bounds = sorted(vert_pos)
    row_bounds = sorted(horiz_pos)

    cells = _make_cells(col_bounds, row_bounds)
    return GridGeometry(
        col_boundaries=col_bounds,
        row_boundaries=row_bounds,
        cells=cells,
        image_width=w,
        image_height=h,
        strategy="line_based",
        strategy_confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Strategy 2: text-box clustering
# ---------------------------------------------------------------------------

def textbox_clustering_reconstruction(
    tokens: List[OcrToken],
    image_width: int = 0,
    image_height: int = 0,
) -> Optional[GridGeometry]:
    """Infer grid structure from OCR token positions."""
    if len(tokens) < 6:
        return None

    avg_h = sum(t.height for t in tokens) / len(tokens)
    avg_w = sum(t.width for t in tokens) / len(tokens)

    col_gap = max(avg_w * 0.8, 12)
    row_gap = max(avg_h * 0.5, 8)

    x_centres = [t.mid_x for t in tokens]
    y_centres = [t.mid_y for t in tokens]

    col_centres = _cluster_1d(x_centres, col_gap)
    row_centres = _cluster_1d(y_centres, row_gap)

    if len(col_centres) < 3 or len(row_centres) < 2:
        return None

    col_margin = avg_w * 0.6
    row_margin = avg_h * 0.6

    col_bounds = _boundaries_from_centres(col_centres, col_margin)
    row_bounds = _boundaries_from_centres(row_centres, row_margin)

    cells = _make_cells(col_bounds, row_bounds)

    n_tokens_assigned = 0
    for t in tokens:
        for c in cells:
            if c.x_min <= t.mid_x <= c.x_max and c.y_min <= t.mid_y <= c.y_max:
                n_tokens_assigned += 1
                break

    coverage = n_tokens_assigned / len(tokens) if tokens else 0.0
    col_score = min(len(col_centres) / 12.0, 1.0)
    row_score = min(len(row_centres) / 5.0, 1.0)
    confidence = 0.4 * coverage + 0.3 * col_score + 0.3 * row_score

    return GridGeometry(
        col_boundaries=col_bounds,
        row_boundaries=row_bounds,
        cells=cells,
        image_width=image_width,
        image_height=image_height,
        strategy="textbox_clustering",
        strategy_confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reconstruct_grid(
    image_bytes: bytes,
    tokens: List[OcrToken],
) -> GridGeometry:
    """Try both strategies and return the one with higher confidence.

    Falls back to text-box clustering if line detection fails entirely.
    """
    buf = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    img_w = img.shape[1] if img is not None else 0
    img_h = img.shape[0] if img is not None else 0

    line_geo = line_based_reconstruction(image_bytes)
    text_geo = textbox_clustering_reconstruction(tokens, img_w, img_h)

    if line_geo and text_geo:
        return line_geo if line_geo.strategy_confidence >= text_geo.strategy_confidence else text_geo
    if line_geo:
        return line_geo
    if text_geo:
        return text_geo

    # Last-resort: build a degenerate geometry from token extents
    if tokens:
        xs = [t.mid_x for t in tokens]
        ys = [t.mid_y for t in tokens]
        return GridGeometry(
            col_boundaries=[min(xs), max(xs)],
            row_boundaries=[min(ys), max(ys)],
            cells=[],
            image_width=img_w,
            image_height=img_h,
            strategy="fallback",
            strategy_confidence=0.0,
        )

    return GridGeometry(
        col_boundaries=[], row_boundaries=[], cells=[],
        image_width=img_w, image_height=img_h,
        strategy="empty", strategy_confidence=0.0,
    )
