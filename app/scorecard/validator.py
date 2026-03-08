"""Constraint-driven validation and repair for scorecard data.

Hard constraints
----------------
- PAR OUT == sum of hole pars (front/back).
- Player OUT/IN == sum of corresponding hole scores.
- TOTAL == OUT + IN (when both halves present).

Soft constraints
----------------
- Hole scores in range 1..15 (flag >15).
- Common OCR confusions: 3<->8, 5<->6, 4<->9, 1<->7, 0<->8.

Repair strategy
---------------
Bounded beam search over lowest-confidence cells.  Each candidate state
replaces a single digit using the confusion map.  The search stops when all
hard constraints pass or a budget (default 30 states) is exhausted.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import CellRepair, CellValue, ParseV2Result, ValidationResult

_INT_RE = re.compile(r"^-?\d+$")

CONFUSION_MAP: Dict[str, List[str]] = {
    "3": ["8"],
    "8": ["3", "0"],
    "5": ["6"],
    "6": ["5"],
    "4": ["9"],
    "9": ["4"],
    "1": ["7"],
    "7": ["1"],
    "0": ["8"],
}


def _try_int(s: str) -> Optional[int]:
    s = s.strip()
    return int(s) if _INT_RE.match(s) else None


def _get_hole_scores(
    result: ParseV2Result,
    player_row: int,
) -> List[Optional[int]]:
    """Read hole-score integers for one player row."""
    if player_row >= len(result.grid_text):
        return []
    row = result.grid_text[player_row]
    return [_try_int(row[c]) if c < len(row) else None for c in result.hole_cols]


def _get_cell(result: ParseV2Result, r: int, c: int) -> str:
    if r < len(result.grid_text) and c < len(result.grid_text[r]):
        return result.grid_text[r][c].strip()
    return ""


def _set_cell(result: ParseV2Result, r: int, c: int, val: str) -> None:
    if r < len(result.grid_text) and c < len(result.grid_text[r]):
        result.grid_text[r][c] = val
        if result.cell_values and r < len(result.cell_values) and c < len(result.cell_values[r]):
            result.cell_values[r][c].best_text = val


# ---------------------------------------------------------------------------
# Hard constraint checkers
# ---------------------------------------------------------------------------

@dataclass
class _Violation:
    kind: str  # "par_sum", "out_sum", "in_sum", "total_sum"
    row: int
    expected: int
    actual: int
    involved_cols: List[int] = field(default_factory=list)


def _check_par_sum(result: ParseV2Result) -> List[_Violation]:
    """Check that par values sum to the displayed OUT/IN/TOTAL par."""
    violations: List[_Violation] = []
    if result.par_row is None:
        return violations

    par_texts = result.grid_text[result.par_row] if result.par_row < len(result.grid_text) else []

    pars = [_try_int(par_texts[c]) if c < len(par_texts) else None for c in result.hole_cols]

    # Determine which holes are front 9 / back 9 based on first_hole_number
    front_cols: List[int] = []
    back_cols: List[int] = []
    for i, c in enumerate(result.hole_cols):
        h = result.first_hole_number + i
        if 1 <= h <= 9:
            front_cols.append(i)
        elif 10 <= h <= 18:
            back_cols.append(i)

    def _check_subtotal(col: Optional[int], idx_list: List[int], kind: str) -> None:
        if col is None:
            return
        displayed = _try_int(par_texts[col]) if col < len(par_texts) else None
        if displayed is None:
            return
        vals = [pars[i] for i in idx_list if pars[i] is not None]
        if len(vals) == len(idx_list) and vals:
            actual = sum(v for v in vals if v is not None)
            if actual != displayed:
                violations.append(_Violation(kind, result.par_row, displayed, actual, [result.hole_cols[i] for i in idx_list]))

    _check_subtotal(result.out_col, front_cols, "par_out_sum")
    _check_subtotal(result.in_col, back_cols, "par_in_sum")

    # For back-9-only cards (all holes are 10-18), the OUT column contains
    # the 9-hole par total — treat it as a back-9 sum check.
    if not front_cols and back_cols and result.out_col is not None:
        _check_subtotal(result.out_col, back_cols, "par_out_sum")

    if result.total_col is not None:
        displayed = _try_int(par_texts[result.total_col]) if result.total_col < len(par_texts) else None
        if displayed is not None:
            all_vals = [p for p in pars if p is not None]
            if len(all_vals) == len(pars) and all_vals:
                actual = sum(all_vals)
                if actual != displayed:
                    violations.append(_Violation("par_total_sum", result.par_row, displayed, actual, list(result.hole_cols)))

    return violations


def _check_player_sums(result: ParseV2Result) -> List[_Violation]:
    """Check OUT/IN/TOTAL consistency for each player row."""
    violations: List[_Violation] = []

    for pr in result.player_rows:
        scores = _get_hole_scores(result, pr)
        row_texts = result.grid_text[pr] if pr < len(result.grid_text) else []

        front_idx: List[int] = []
        back_idx: List[int] = []
        for i in range(len(result.hole_cols)):
            h = result.first_hole_number + i
            if 1 <= h <= 9:
                front_idx.append(i)
            elif 10 <= h <= 18:
                back_idx.append(i)

        def _check(col: Optional[int], idx_list: List[int], kind: str) -> None:
            if col is None or col >= len(row_texts):
                return
            displayed = _try_int(row_texts[col])
            if displayed is None:
                return
            vals = [scores[i] for i in idx_list if i < len(scores) and scores[i] is not None]
            if len(vals) == len(idx_list) and vals:
                actual = sum(v for v in vals if v is not None)
                if actual != displayed:
                    violations.append(_Violation(kind, pr, displayed, actual, [result.hole_cols[i] for i in idx_list]))

        _check(result.out_col, front_idx, "player_out_sum")
        _check(result.in_col, back_idx, "player_in_sum")

        # For back-9-only cards, the OUT column is the 9-hole total.
        if not front_idx and back_idx:
            _check(result.out_col, back_idx, "player_out_sum")

        if result.total_col is not None and result.total_col < len(row_texts):
            displayed_total = _try_int(row_texts[result.total_col])
            if displayed_total is not None:
                out_val = _try_int(row_texts[result.out_col]) if result.out_col is not None and result.out_col < len(row_texts) else None
                in_val = _try_int(row_texts[result.in_col]) if result.in_col is not None and result.in_col < len(row_texts) else None
                if out_val is not None and in_val is not None:
                    if out_val + in_val != displayed_total:
                        violations.append(_Violation("player_total_sum", pr, displayed_total, out_val + in_val, []))
                elif out_val is not None and in_val is None:
                    all_scores = [s for s in scores if s is not None]
                    if len(all_scores) == len(scores) and all_scores:
                        actual = sum(all_scores)
                        if actual != displayed_total:
                            violations.append(_Violation("player_total_sum", pr, displayed_total, actual, list(result.hole_cols)))

    return violations


# ---------------------------------------------------------------------------
# Soft constraint checks
# ---------------------------------------------------------------------------

def _check_score_ranges(result: ParseV2Result) -> Dict[str, str]:
    """Flag implausible hole scores."""
    warnings: Dict[str, str] = {}
    for pr in result.player_rows:
        scores = _get_hole_scores(result, pr)
        for i, s in enumerate(scores):
            if s is not None and s > 15:
                col = result.hole_cols[i] if i < len(result.hole_cols) else -1
                warnings[f"r{pr}c{col}"] = f"Score {s} is unusually high"
    return warnings


# ---------------------------------------------------------------------------
# Repair engine
# ---------------------------------------------------------------------------

def _confusion_alternatives(digit_str: str) -> List[str]:
    """Generate single-digit substitution candidates from the confusion map."""
    alts: List[str] = []
    for i, ch in enumerate(digit_str):
        for repl in CONFUSION_MAP.get(ch, []):
            alt = digit_str[:i] + repl + digit_str[i + 1:]
            alts.append(alt)
    return alts


@dataclass
class _SearchState:
    result: ParseV2Result
    repairs: List[CellRepair]
    cost: float


def _repair_violations(
    result: ParseV2Result,
    violations: List[_Violation],
    beam_width: int = 30,
) -> Tuple[ParseV2Result, List[CellRepair]]:
    """Attempt to fix violations by substituting lowest-confidence cells.

    Uses a bounded beam search.
    """
    if not violations:
        return result, []

    # Collect mutable cells: hole-score cells in player rows and par row
    mutable_cells: List[Tuple[int, int, float]] = []
    for pr in result.player_rows:
        for c in result.hole_cols:
            conf = 1.0
            if result.cell_values and pr < len(result.cell_values) and c < len(result.cell_values[pr]):
                conf = result.cell_values[pr][c].confidence
            text = _get_cell(result, pr, c)
            if _INT_RE.match(text.strip()):
                mutable_cells.append((pr, c, conf))

    if result.par_row is not None:
        for c in result.hole_cols:
            conf = 1.0
            if result.cell_values and result.par_row < len(result.cell_values) and c < len(result.cell_values[result.par_row]):
                conf = result.cell_values[result.par_row][c].confidence
            text = _get_cell(result, result.par_row, c)
            if _INT_RE.match(text.strip()):
                mutable_cells.append((result.par_row, c, conf))

    # Sort by confidence ascending (repair lowest confidence first)
    mutable_cells.sort(key=lambda x: x[2])

    initial = _SearchState(result=result, repairs=[], cost=0.0)
    beam: List[_SearchState] = [initial]

    for r, c, conf in mutable_cells[:beam_width]:
        next_beam: List[_SearchState] = []
        for state in beam:
            old_val = _get_cell(state.result, r, c).strip()
            if not _INT_RE.match(old_val):
                next_beam.append(state)
                continue

            next_beam.append(state)

            for alt in _confusion_alternatives(old_val):
                new_result = ParseV2Result(
                    grid_text=[row[:] for row in state.result.grid_text],
                    cell_values=state.result.cell_values,
                    geometry=state.result.geometry,
                    validation=state.result.validation,
                    overall_confidence=state.result.overall_confidence,
                    hole_row=state.result.hole_row,
                    par_row=state.result.par_row,
                    si_row=state.result.si_row,
                    player_rows=state.result.player_rows,
                    hole_cols=state.result.hole_cols,
                    out_col=state.result.out_col,
                    in_col=state.result.in_col,
                    total_col=state.result.total_col,
                    name_col=state.result.name_col,
                    first_hole_number=state.result.first_hole_number,
                )
                _set_cell(new_result, r, c, alt)

                repair = CellRepair(row=r, col=c, old_value=old_val, new_value=alt,
                                    reason=f"OCR confusion {old_val}->{alt}")
                new_repairs = state.repairs + [repair]
                cost = state.cost + (1.0 - conf)

                new_violations = _check_par_sum(new_result) + _check_player_sums(new_result)
                if not new_violations:
                    return new_result, new_repairs

                next_beam.append(_SearchState(new_result, new_repairs, cost))

        next_beam.sort(key=lambda s: (
            len(_check_par_sum(s.result) + _check_player_sums(s.result)),
            s.cost,
        ))
        beam = next_beam[:beam_width]

    if beam:
        best = beam[0]
        return best.result, best.repairs
    return result, []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_and_repair(
    result: ParseV2Result,
    beam_width: int = 30,
) -> ValidationResult:
    """Run all constraints, attempt repairs, and return validation outcome."""
    violations = _check_par_sum(result) + _check_player_sums(result)
    soft_warnings = _check_score_ranges(result)

    if not violations:
        return ValidationResult(
            is_consistent=True,
            repairs=[],
            needs_review=bool(soft_warnings),
            warnings=soft_warnings,
        )

    repaired_result, repairs = _repair_violations(result, violations, beam_width)

    # Copy repaired grid text back
    result.grid_text = repaired_result.grid_text

    remaining = _check_par_sum(result) + _check_player_sums(result)
    soft_warnings.update(_check_score_ranges(result))

    for v in remaining:
        soft_warnings[f"{v.kind}_r{v.row}"] = f"Expected {v.expected}, got {v.actual}"

    return ValidationResult(
        is_consistent=len(remaining) == 0,
        repairs=repairs,
        needs_review=len(remaining) > 0 or bool(soft_warnings),
        warnings=soft_warnings,
    )
