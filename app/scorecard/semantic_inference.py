"""Semantic inference: identify hole headers, par/SI, player rows from grid cells.

Uses the grid geometry to constrain inference rather than relying on
free-form heuristics alone.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .models import CellValue, ParseV2Result

_INT_RE = re.compile(r"^-?\d+$")
_HOLE_NUMBERS_18 = frozenset(str(i) for i in range(1, 19))
_TOTAL_KW = {"total", "gross", "net", "score", "tot"}
_PAR_KW = {"par"}
_SI_KW = {"si", "hcp", "handicap", "stroke", "index"}
_SKIP_ROW_KW = {
    "par", "si", "hcp", "handicap", "stroke", "index",
    "print", "continue", "scorecard", "leaderboard",
    "stats", "round", "dell", "wins", ">",
    "single", "team", "hole", "holes",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().lower())


def _try_int(text: str) -> Optional[int]:
    s = text.strip()
    return int(s) if _INT_RE.match(s) else None


def _row_texts(cells: List[List[CellValue]], r: int) -> List[str]:
    if r < 0 or r >= len(cells):
        return []
    return [cv.best_text.strip() for cv in cells[r]]


def _col_texts(cells: List[List[CellValue]], c: int) -> List[str]:
    return [cells[r][c].best_text.strip() for r in range(len(cells)) if c < len(cells[r])]


# ---------------------------------------------------------------------------
# Hole-number row detection
# ---------------------------------------------------------------------------

def _score_hole_row(texts: List[str]) -> Tuple[float, int]:
    """Score how likely a row is the hole-number header.

    Returns (score, first_hole_number).
    """
    nums = []
    for t in texts:
        v = _try_int(t)
        if v is not None:
            nums.append(v)

    if len(nums) < 3:
        return 0.0, 1

    in_range = sum(1 for n in nums if 1 <= n <= 18)
    fraction = in_range / len(texts)

    # Check monotonicity
    mono = sum(1 for i in range(len(nums) - 1) if nums[i + 1] > nums[i])
    mono_score = mono / max(len(nums) - 1, 1)

    score = 0.5 * fraction + 0.5 * mono_score

    first = nums[0] if nums else 1
    if first < 1:
        first = 1
    if first > 10:
        first = 10

    return score, first


# ---------------------------------------------------------------------------
# OUT / IN / TOTAL column detection
# ---------------------------------------------------------------------------

def _find_keyword_cols(
    cells: List[List[CellValue]],
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Scan all cells for OUT/IN/TOTAL column header keywords.

    Only the literal labels "OUT" and "IN" are used to identify subtotal
    columns.  Section-heading labels like "B9", "F9", "FRONT", "BACK" can
    appear anywhere on a scorecard and must not be mistaken for column
    headers.
    """
    out_col: Optional[int] = None
    in_col: Optional[int] = None
    total_col: Optional[int] = None

    for row in cells:
        for cv in row:
            n = _norm(cv.best_text)
            if n == "out":
                out_col = cv.col
            elif n == "in":
                in_col = cv.col
            elif n in _TOTAL_KW:
                total_col = cv.col

    return out_col, in_col, total_col


# ---------------------------------------------------------------------------
# PAR / SI row detection
# ---------------------------------------------------------------------------

def _score_par_row(texts: List[str], hole_cols: List[int]) -> float:
    """Score how likely texts at hole columns are par values."""
    if not hole_cols:
        return 0.0
    vals = [_try_int(texts[c]) for c in hole_cols if c < len(texts)]
    par_ok = sum(1 for v in vals if v is not None and 3 <= v <= 5)
    return par_ok / max(len(vals), 1)


def _score_si_row(texts: List[str], hole_cols: List[int]) -> float:
    """Score how likely texts at hole columns are stroke-index values."""
    if not hole_cols:
        return 0.0
    vals = [_try_int(texts[c]) for c in hole_cols if c < len(texts)]
    si_vals = [v for v in vals if v is not None and 1 <= v <= 18]
    if not si_vals:
        return 0.0
    unique_frac = len(set(si_vals)) / max(len(si_vals), 1)
    count_frac = len(si_vals) / max(len(vals), 1)
    return count_frac * unique_frac


# ---------------------------------------------------------------------------
# Player row detection
# ---------------------------------------------------------------------------

def _is_player_row(
    texts: List[str],
    hole_cols: List[int],
    name_col: int,
) -> bool:
    """Heuristic: player rows have a non-empty name and mostly numeric hole cells."""
    if name_col >= len(texts):
        return False
    name = texts[name_col].strip()
    if not name or _norm(name) in _SKIP_ROW_KW:
        return False

    vals = [_try_int(texts[c]) for c in hole_cols if c < len(texts)]
    numeric_count = sum(1 for v in vals if v is not None)
    if not vals:
        return bool(name)

    score_range = sum(1 for v in vals if v is not None and 1 <= v <= 15)
    return numeric_count >= 2 and score_range / max(len(vals), 1) >= 0.3


# ---------------------------------------------------------------------------
# Name column detection
# ---------------------------------------------------------------------------

def _find_name_col(cells: List[List[CellValue]], hole_cols: List[int]) -> int:
    """Identify the name column as the non-numeric column outside hole_cols."""
    if not cells or not cells[0]:
        return 0

    hole_set = set(hole_cols)
    n_cols = len(cells[0])

    best_col = 0
    best_alpha = 0

    for c in range(n_cols):
        if c in hole_set:
            continue
        alpha_count = 0
        for r in range(len(cells)):
            if c < len(cells[r]):
                t = cells[r][c].best_text.strip()
                if t and not _INT_RE.match(t):
                    alpha_count += 1
        if alpha_count > best_alpha:
            best_alpha = alpha_count
            best_col = c

    return best_col


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def infer_semantics(cells: List[List[CellValue]]) -> ParseV2Result:
    """Analyse the cell grid and identify semantic roles for rows/columns.

    Returns a :class:`ParseV2Result` populated with row/column labels and
    the text grid.
    """
    result = ParseV2Result()

    if not cells:
        return result

    n_rows = len(cells)
    n_cols = max(len(r) for r in cells) if cells else 0

    result.grid_text = [[cv.best_text for cv in row] for row in cells]
    result.cell_values = cells

    # --- Hole row ---
    best_hole_score = 0.0
    best_hole_row = -1
    best_first_hole = 1

    for r in range(n_rows):
        texts = _row_texts(cells, r)
        score, first_h = _score_hole_row(texts)
        if score > best_hole_score:
            best_hole_score = score
            best_hole_row = r
            best_first_hole = first_h

    if best_hole_score >= 0.3:
        result.hole_row = best_hole_row
        result.first_hole_number = best_first_hole

    # --- Hole columns ---
    if result.hole_row is not None:
        texts = _row_texts(cells, result.hole_row)
        for c, t in enumerate(texts):
            v = _try_int(t)
            if v is not None and 1 <= v <= 18:
                result.hole_cols.append(c)
    else:
        # Fallback: columns with mostly numeric values in [1..15]
        for c in range(n_cols):
            col_vals = _col_texts(cells, c)
            numeric = [_try_int(v) for v in col_vals]
            score_range = sum(1 for v in numeric if v is not None and 1 <= v <= 15)
            if score_range >= max(n_rows * 0.3, 2):
                result.hole_cols.append(c)

    # --- OUT / IN / TOTAL columns ---
    out_col, in_col, total_col = _find_keyword_cols(cells)
    result.out_col = out_col
    result.in_col = in_col
    result.total_col = total_col

    # --- Name column ---
    result.name_col = _find_name_col(cells, result.hole_cols)

    # --- PAR / SI rows ---
    # Par and SI rows always appear close to the hole-number header row.
    # Restrict the search window so that distant player-score rows cannot
    # be misidentified as par/SI.
    if result.hole_row is not None:
        par_si_start = max(0, result.hole_row - 3)
        par_si_end = min(n_rows, result.hole_row + 7)
    else:
        par_si_start, par_si_end = 0, n_rows

    # First pass: keyword-based detection (highest priority)
    par_by_keyword = False
    si_by_keyword = False

    for r in range(par_si_start, par_si_end):
        if r == result.hole_row:
            continue
        texts = _row_texts(cells, r)
        first_cell = _norm(texts[0]) if texts else ""
        name_cell = _norm(texts[result.name_col]) if result.name_col is not None and result.name_col < len(texts) else ""

        if first_cell in _PAR_KW or name_cell in _PAR_KW:
            result.par_row = r
            par_by_keyword = True
        elif first_cell in _SI_KW or name_cell in _SI_KW:
            result.si_row = r
            si_by_keyword = True

    # Second pass: numeric scoring fallback (only if keyword didn't match)
    # Still restricted to the same proximity window.
    best_par_score = 0.0
    best_si_score = 0.0

    if not par_by_keyword or not si_by_keyword:
        for r in range(par_si_start, par_si_end):
            if r == result.hole_row or r == result.par_row or r == result.si_row:
                continue
            texts = _row_texts(cells, r)

            if not par_by_keyword:
                ps = _score_par_row(texts, result.hole_cols)
                if ps > best_par_score and ps >= 0.5:
                    best_par_score = ps
                    result.par_row = r

            if not si_by_keyword:
                ss = _score_si_row(texts, result.hole_cols)
                if ss > best_si_score and ss >= 0.3:
                    best_si_score = ss
                    result.si_row = r

    # Ensure par and si are different rows
    if result.par_row is not None and result.par_row == result.si_row:
        result.si_row = None

    # --- Player rows ---
    skip_rows = {result.hole_row, result.par_row, result.si_row}
    name_col = result.name_col if result.name_col is not None else 0

    for r in range(n_rows):
        if r in skip_rows:
            continue
        texts = _row_texts(cells, r)
        if _is_player_row(texts, result.hole_cols, name_col):
            result.player_rows.append(r)

    return result
