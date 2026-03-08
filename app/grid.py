"""
Grid-based scorecard mapping: extract OCR text into a rows/columns grid,
then apply a user-defined column mapping to produce a DraftRound.
"""
from __future__ import annotations

import re
from typing import List, Optional, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from .vision_ocr import WordBox


class ScorecardGrid(BaseModel):
    rows: List[List[str]]


class GridMapping(BaseModel):
    header_row: Optional[int] = None
    name_col: int = 0
    hole_cols: List[int] = []
    total_col: Optional[int] = None
    out_col: Optional[int] = None
    in_col: Optional[int] = None
    first_player_row: int = 0
    last_player_row: Optional[int] = None
    first_hole_number: int = 1
    par_row: Optional[int] = None
    stroke_index_row: Optional[int] = None


class MapGridRequest(BaseModel):
    grid: ScorecardGrid
    mapping: GridMapping


_INT_RE = re.compile(r"^-?\d+$")


def text_to_grid(text: str) -> ScorecardGrid:
    """Fallback: split raw OCR text into rows by newline, columns by whitespace."""
    rows: List[List[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(stripped.split())
    return ScorecardGrid(rows=rows)


def word_boxes_to_grid(words: List["WordBox"]) -> ScorecardGrid:
    """
    Build a grid that mirrors the visual scorecard layout.  Try both axis
    orientations (normal Y-rows/X-cols and swapped X-rows/Y-cols) and pick
    whichever produces a wider-than-tall grid, which is the expected shape
    for a scorecard.
    """
    if not words:
        return ScorecardGrid(rows=[])

    grid_normal = _build_grid_with_axes(words, row_attr="mid_y", col_attr="mid_x", reverse_rows=False, reverse_cols=False)
    grid_swapped = _build_grid_with_axes(words, row_attr="mid_x", col_attr="mid_y", reverse_rows=False, reverse_cols=True)

    def _col_count(g: ScorecardGrid) -> int:
        return max((len(r) for r in g.rows), default=0)

    n_ratio = _col_count(grid_normal) / max(len(grid_normal.rows), 1)
    s_ratio = _col_count(grid_swapped) / max(len(grid_swapped.rows), 1)

    return grid_swapped if s_ratio > n_ratio else grid_normal


def _build_grid_with_axes(
    words: List["WordBox"],
    row_attr: str,
    col_attr: str,
    reverse_rows: bool,
    reverse_cols: bool,
) -> ScorecardGrid:
    """Build a grid by clustering on one axis for rows and using the other for columns."""
    row_groups = _cluster_into_rows(words, row_attr=row_attr, col_attr=col_attr)
    col_boundaries = _find_column_boundaries(row_groups, col_attr=col_attr)

    if not col_boundaries:
        return ScorecardGrid(rows=[])

    rows: List[List[str]] = []
    for group in row_groups:
        row_cells = [""] * len(col_boundaries)
        for wb in group:
            val = getattr(wb, col_attr)
            ci = _assign_column(val, col_boundaries)
            if row_cells[ci]:
                row_cells[ci] += " " + wb.text
            else:
                row_cells[ci] = wb.text
        rows.append(row_cells)

    if reverse_rows:
        rows.reverse()
    if reverse_cols:
        rows = [row[::-1] for row in rows]

    return ScorecardGrid(rows=rows)


def _cluster_into_rows(
    words: List["WordBox"],
    row_attr: str = "mid_y",
    col_attr: str = "mid_x",
) -> List[List["WordBox"]]:
    """
    Cluster words into rows based on the given row axis.
    Words whose positions on the row axis are within half the typical word
    height of each other belong to the same row.
    """
    if not words:
        return []

    sorted_words = sorted(words, key=lambda w: getattr(w, row_attr))

    avg_height = sum(w.max_y - w.min_y for w in words) / len(words)
    row_tolerance = max(avg_height * 0.45, 5)

    rows: List[List["WordBox"]] = []
    current_row: List["WordBox"] = [sorted_words[0]]
    current_val = getattr(sorted_words[0], row_attr)

    for w in sorted_words[1:]:
        w_val = getattr(w, row_attr)
        if abs(w_val - current_val) <= row_tolerance:
            current_row.append(w)
            current_val = sum(getattr(ww, row_attr) for ww in current_row) / len(current_row)
        else:
            current_row.sort(key=lambda ww: getattr(ww, col_attr))
            rows.append(current_row)
            current_row = [w]
            current_val = w_val

    if current_row:
        current_row.sort(key=lambda ww: getattr(ww, col_attr))
        rows.append(current_row)

    return rows


def _find_column_boundaries(
    row_groups: List[List["WordBox"]],
    col_attr: str = "mid_x",
) -> List[float]:
    """
    Determine column center positions by collecting all word positions on the
    column axis and clustering them.
    """
    all_vals: List[float] = []
    for group in row_groups:
        for w in group:
            all_vals.append(getattr(w, col_attr))
    if not all_vals:
        return []

    all_vals.sort()

    all_heights: List[float] = []
    for group in row_groups:
        for w in group:
            all_heights.append(w.max_y - w.min_y)
    avg_char_width = (sum(all_heights) / len(all_heights) * 1.5) if all_heights else 20

    col_tolerance = max(avg_char_width * 0.8, 15)

    col_centers: List[float] = []
    cluster: List[float] = [all_vals[0]]

    for v in all_vals[1:]:
        if v - (sum(cluster) / len(cluster)) <= col_tolerance:
            cluster.append(v)
        else:
            col_centers.append(sum(cluster) / len(cluster))
            cluster = [v]
    if cluster:
        col_centers.append(sum(cluster) / len(cluster))

    return col_centers


def _assign_column(val: float, col_centers: List[float]) -> int:
    """Return the index of the closest column center."""
    best_idx = 0
    best_dist = abs(val - col_centers[0])
    for i, cx in enumerate(col_centers[1:], 1):
        d = abs(val - cx)
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx


def apply_grid_mapping(grid: ScorecardGrid, mapping: GridMapping) -> dict:
    """
    Walk the grid using the mapping and return a DraftRound-shaped dict
    (same shape as the API DraftRound so the frontend can use it directly).

    Returns a dict with keys: players (list of PlayerDraft-shaped dicts).
    """
    rows = grid.rows
    last_row = mapping.last_player_row if mapping.last_player_row is not None else len(rows) - 1
    last_row = max(last_row, mapping.first_player_row)

    players = []
    for row_idx in range(mapping.first_player_row, last_row + 1):
        if row_idx < 0 or row_idx >= len(rows):
            continue
        row = rows[row_idx]

        if mapping.header_row is not None and row_idx == mapping.header_row:
            continue

        name = _safe_get(row, mapping.name_col, "").strip()
        if not name:
            continue

        hole_map = {}
        for i, col_idx in enumerate(mapping.hole_cols):
            hole_num = mapping.first_hole_number + i
            if 1 <= hole_num <= 18:
                hole_map[hole_num] = _try_int(_safe_get(row, col_idx, ""))

        hole_scores = [
            {"hole_number": h, "score": hole_map.get(h)}
            for h in range(1, 19)
        ]

        total_score = None
        if mapping.total_col is not None:
            total_score = _try_int(_safe_get(row, mapping.total_col, ""))
        out_score = None
        if mapping.out_col is not None:
            out_score = _try_int(_safe_get(row, mapping.out_col, ""))
        in_score = None
        if mapping.in_col is not None:
            in_score = _try_int(_safe_get(row, mapping.in_col, ""))

        stats = {
            "total_score": total_score,
            "out_score": out_score,
            "in_score": in_score,
            "fairways_hit": None,
            "fairways_possible": None,
            "gir": None,
            "gir_possible": None,
            "avg_drive_distance": None,
            "total_putts": None,
            "scramble_successes": None,
            "scramble_opportunities": None,
            "sand_save_successes": None,
            "sand_save_opportunities": None,
        }

        players.append({
            "name": name,
            "team_name": None,
            "hole_scores": hole_scores,
            "stats": stats,
        })

    hole_pars: List[Optional[int]] = [None] * 18
    stroke_indexes: List[Optional[int]] = [None] * 18

    if mapping.par_row is not None and 0 <= mapping.par_row < len(rows):
        par_row_data = rows[mapping.par_row]
        for i, col_idx in enumerate(mapping.hole_cols):
            hole_num = mapping.first_hole_number + i
            if 1 <= hole_num <= 18:
                val = _try_int(_safe_get(par_row_data, col_idx, ""))
                if val is not None and 3 <= val <= 5:
                    hole_pars[hole_num - 1] = val

    if mapping.stroke_index_row is not None and 0 <= mapping.stroke_index_row < len(rows):
        si_row_data = rows[mapping.stroke_index_row]
        for i, col_idx in enumerate(mapping.hole_cols):
            hole_num = mapping.first_hole_number + i
            if 1 <= hole_num <= 18:
                val = _try_int(_safe_get(si_row_data, col_idx, ""))
                if val is not None and 1 <= val <= 18:
                    stroke_indexes[hole_num - 1] = val

    return {
        "date": None,
        "course_name": None,
        "tee_set": None,
        "is_team_round": False,
        "players": players,
        "hole_pars": hole_pars,
        "stroke_indexes": stroke_indexes,
    }


def _safe_get(row: List[str], idx: int, default: str = "") -> str:
    if 0 <= idx < len(row):
        return row[idx]
    return default


def _try_int(s: str) -> Optional[int]:
    s = s.strip()
    if _INT_RE.match(s):
        return int(s)
    return None


def normalize_cell(text: str) -> str:
    """Clean up common OCR artifacts in a single grid cell."""
    s = text.strip()
    s = s.replace("|", "").replace("\\", "")
    s = s.strip(".,;:'\"")
    return s


def pad_grid_rows(grid: ScorecardGrid) -> ScorecardGrid:
    """Pad all rows to the same length with empty strings."""
    if not grid.rows:
        return grid
    max_cols = max(len(r) for r in grid.rows)
    return ScorecardGrid(rows=[r + [""] * (max_cols - len(r)) for r in grid.rows])


def clean_grid(grid: ScorecardGrid) -> ScorecardGrid:
    """Normalize cells, drop fully-empty rows, and pad to uniform width."""
    rows = []
    for row in grid.rows:
        cleaned = [normalize_cell(c) for c in row]
        if any(c for c in cleaned):
            rows.append(cleaned)
    return pad_grid_rows(ScorecardGrid(rows=rows))


def suggest_par_and_si_rows(grid: ScorecardGrid, mapping: GridMapping) -> tuple[Optional[int], Optional[int]]:
    """
    Heuristic: find rows that look like par (values mostly 3–5) and
    stroke index (values 1–18, many unique). Only considers rows above
    the first player row. Returns (par_row, stroke_index_row) or (None, None).
    """
    rows = grid.rows
    if not rows or not mapping.hole_cols:
        return (None, None)

    header = mapping.header_row if mapping.header_row is not None else -1
    first_player = mapping.first_player_row
    hole_cols = mapping.hole_cols

    def get_ints_in_hole_cols(row_idx: int) -> list[Optional[int]]:
        if row_idx < 0 or row_idx >= len(rows):
            return []
        row = rows[row_idx]
        return [_try_int(_safe_get(row, c, "")) for c in hole_cols]

    best_par_row: Optional[int] = None
    best_par_score = 0.0
    best_si_row: Optional[int] = None
    best_si_score = 0.0

    for ri in range(min(first_player, len(rows))):
        if ri == header:
            continue
        vals = get_ints_in_hole_cols(ri)
        if not vals:
            continue

        par_ok = sum(1 for v in vals if v is not None and 3 <= v <= 5)
        par_score = par_ok / max(len(vals), 1)
        if par_score >= 0.6 and par_ok >= 3 and par_score > best_par_score:
            best_par_score = par_score
            best_par_row = ri

        si_vals = [v for v in vals if v is not None and 1 <= v <= 18]
        unique = len(set(si_vals))
        si_score = (len(si_vals) / max(len(vals), 1)) * (unique / max(len(si_vals), 1))
        if si_score >= 0.4 and unique >= 3 and si_score > best_si_score:
            best_si_score = si_score
            best_si_row = ri

    return (best_par_row, best_si_row)
