"""Assign OCR tokens to grid cells and produce ranked CellValues."""
from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple

from .models import CellCandidate, CellRect, CellValue, GridGeometry, OcrToken

_NUMERIC_RE = re.compile(r"^-?\d+$")


def _cell_center(cell: CellRect) -> Tuple[float, float]:
    return ((cell.x_min + cell.x_max) / 2, (cell.y_min + cell.y_max) / 2)


def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _find_cell(token: OcrToken, cells: List[CellRect]) -> int:
    """Return index of the cell whose bounds contain the token centre,
    or the nearest cell if the token falls outside all cells."""
    best_idx = -1
    best_dist = float("inf")
    for i, c in enumerate(cells):
        if c.x_min <= token.mid_x <= c.x_max and c.y_min <= token.mid_y <= c.y_max:
            d = _distance(token.center, _cell_center(c))
            if d < best_dist:
                best_dist = d
                best_idx = i
    if best_idx >= 0:
        return best_idx
    for i, c in enumerate(cells):
        d = _distance(token.center, _cell_center(c))
        if d < best_dist:
            best_dist = d
            best_idx = i
    return max(best_idx, 0)


def assign_tokens(
    tokens: List[OcrToken],
    geometry: GridGeometry,
) -> List[List[CellValue]]:
    """Map every token into a grid cell, then resolve each cell's best text.

    Returns a 2-D list ``[row][col]`` of :class:`CellValue`.
    """
    if not geometry.cells or not tokens:
        return []

    n_rows = geometry.n_rows
    n_cols = geometry.n_cols
    if n_rows == 0 or n_cols == 0:
        return []

    buckets: Dict[Tuple[int, int], List[CellCandidate]] = {}

    for token in tokens:
        idx = _find_cell(token, geometry.cells)
        cell = geometry.cells[idx]
        center = _cell_center(cell)
        dist = _distance(token.center, center)
        is_num = bool(_NUMERIC_RE.match(token.text.strip()))
        cand = CellCandidate(
            text=token.text.strip(),
            confidence=token.confidence,
            distance_to_center=dist,
            is_numeric=is_num,
            box_height=token.height,
        )
        key = (cell.row, cell.col)
        buckets.setdefault(key, []).append(cand)

    # Sort candidates: confidence desc, distance asc, numeric first
    for key in buckets:
        buckets[key].sort(key=lambda c: (-c.confidence, c.distance_to_center, not c.is_numeric))

    result: List[List[CellValue]] = []
    for r in range(n_rows):
        row_vals: List[CellValue] = []
        for c in range(n_cols):
            cands = buckets.get((r, c), [])
            if cands:
                best = cands[0]
                # Merge text from all candidates in the cell (left-to-right order preserved by distance)
                merged = " ".join(cd.text for cd in cands) if len(cands) > 1 else best.text
                conf = best.confidence
            else:
                merged = ""
                conf = 0.0
            row_vals.append(CellValue(
                row=r, col=c,
                best_text=merged,
                confidence=conf,
                candidates=cands,
            ))
        result.append(row_vals)

    return result
