"""Scorecard parse v2 orchestrator.

Coordinates the full layout-first pipeline:
  panel detection -> grid reconstruction -> token assignment ->
  semantic inference -> validation/repair -> adapt to DraftRound.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from ..grid import GridMapping, ScorecardGrid, apply_grid_mapping
from ..vision_ocr import WordBox
from .debug import build_debug_payload, render_debug_overlay
from .grid_reconstruction import reconstruct_grid
from .models import (
    CellRepair,
    CellValue,
    DebugLayout,
    GridGeometry,
    OcrToken,
    ParseV2Result,
    ValidationResult,
)
from .panel_detection import detect_and_normalise
from .semantic_inference import infer_semantics
from .token_assignment import assign_tokens
from .validator import validate_and_repair

_INT_RE = re.compile(r"^-?\d+$")


def _extract_player_name(row: List[str], first_hole_col: int) -> str:
    """Build a display name from all cells to the left of the first hole column.

    Handles multi-cell labels like ["2", "TEAM", "1"] → "TEAM 1".
    The leading rank/order number (e.g. the "2" that appears to the left of
    "TEAM 1") is stripped when a "TEAM N" pattern is found so that names
    come out as "TEAM 1", "TEAM 2", etc.
    """
    parts = [
        row[c].strip()
        for c in range(min(first_hole_col, len(row)))
        if row[c].strip()
    ]
    if not parts:
        return ""
    # Look for "TEAM <digit>" pattern anywhere in the parts list
    for i, p in enumerate(parts):
        if p.upper() == "TEAM" and i + 1 < len(parts) and _INT_RE.match(parts[i + 1]):
            return f"TEAM {parts[i + 1]}"
    # Fallback: prefer non-numeric tokens, else join everything
    non_num = [p for p in parts if not _INT_RE.match(p)]
    return " ".join(non_num) if non_num else " ".join(parts)


# ---------------------------------------------------------------------------
# WordBox / OcrToken conversion helpers
# ---------------------------------------------------------------------------

def wordboxes_to_tokens(boxes: List[WordBox]) -> List[OcrToken]:
    """Convert v1 WordBox list into enriched OcrToken list.

    WordBox only has mid_x/mid_y and min_y/max_y.  We estimate min_x/max_x
    from the text length and average character width derived from height.
    """
    tokens: List[OcrToken] = []
    for wb in boxes:
        char_w = (wb.max_y - wb.min_y) * 0.6
        est_width = max(len(wb.text) * char_w, char_w)
        tokens.append(OcrToken(
            text=wb.text,
            mid_x=wb.mid_x,
            mid_y=wb.mid_y,
            min_x=wb.mid_x - est_width / 2,
            max_x=wb.mid_x + est_width / 2,
            min_y=wb.min_y,
            max_y=wb.max_y,
            confidence=1.0,
        ))
    return tokens


# ---------------------------------------------------------------------------
# Adapter: ParseV2Result → existing DraftRound-shaped dict
# ---------------------------------------------------------------------------

def _try_int(s: str) -> Optional[int]:
    s = s.strip()
    return int(s) if _INT_RE.match(s) else None


def _adapt_to_draft_round(
    result: ParseV2Result,
    validation: ValidationResult,
    image_date: Optional[date] = None,
) -> dict:
    """Convert v2 result into the same dict shape as ``apply_grid_mapping``.

    Keys: date, course_name, tee_set, is_team_round, players, hole_pars,
    stroke_indexes, scorecard_grid, predicted_mapping, prediction_meta.
    """
    grid_text = result.grid_text
    n_cols = max((len(r) for r in grid_text), default=0)

    # Build ScorecardGrid for compatibility
    scorecard_grid = ScorecardGrid(rows=[row[:] for row in grid_text])

    # Build GridMapping for compatibility
    mapping = GridMapping(
        header_row=result.hole_row,
        name_col=result.name_col if result.name_col is not None else 0,
        hole_cols=list(result.hole_cols),
        total_col=result.total_col,
        out_col=result.out_col,
        in_col=result.in_col,
        first_player_row=result.player_rows[0] if result.player_rows else 0,
        last_player_row=result.player_rows[-1] if result.player_rows else None,
        first_hole_number=result.first_hole_number,
        par_row=result.par_row,
        stroke_index_row=result.si_row,
    )

    # Build players list
    players: List[dict] = []
    first_hole_col = min(result.hole_cols) if result.hole_cols else 1

    for pr in result.player_rows:
        if pr >= len(grid_text):
            continue
        row = grid_text[pr]

        name = _extract_player_name(row, first_hole_col)
        if not name:
            # Last-resort: fall back to the single name_col cell
            name_col = result.name_col if result.name_col is not None else 0
            name = row[name_col].strip() if name_col < len(row) else ""
        if not name:
            continue

        hole_map: Dict[int, Optional[int]] = {}
        for i, c in enumerate(result.hole_cols):
            hole_num = result.first_hole_number + i
            if 1 <= hole_num <= 18 and c < len(row):
                hole_map[hole_num] = _try_int(row[c])

        hole_scores = [
            {"hole_number": h, "score": hole_map.get(h)}
            for h in range(1, 19)
        ]

        total_score = _try_int(row[result.total_col]) if result.total_col is not None and result.total_col < len(row) else None
        out_score = _try_int(row[result.out_col]) if result.out_col is not None and result.out_col < len(row) else None
        in_score = _try_int(row[result.in_col]) if result.in_col is not None and result.in_col < len(row) else None

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

    # Build hole pars
    hole_pars: List[Optional[int]] = [None] * 18
    if result.par_row is not None and result.par_row < len(grid_text):
        par_row_data = grid_text[result.par_row]
        for i, c in enumerate(result.hole_cols):
            hole_num = result.first_hole_number + i
            if 1 <= hole_num <= 18 and c < len(par_row_data):
                val = _try_int(par_row_data[c])
                if val is not None and 3 <= val <= 5:
                    hole_pars[hole_num - 1] = val

    # Build stroke indexes
    stroke_indexes: List[Optional[int]] = [None] * 18
    if result.si_row is not None and result.si_row < len(grid_text):
        si_row_data = grid_text[result.si_row]
        for i, c in enumerate(result.hole_cols):
            hole_num = result.first_hole_number + i
            if 1 <= hole_num <= 18 and c < len(si_row_data):
                val = _try_int(si_row_data[c])
                if val is not None and 1 <= val <= 18:
                    stroke_indexes[hole_num - 1] = val

    # Build prediction_meta
    field_warnings: Dict[str, str] = {}
    if validation.warnings:
        field_warnings.update(validation.warnings)
    if validation.repairs:
        for rep in validation.repairs:
            field_warnings[f"repair_r{rep.row}c{rep.col}"] = (
                f"Auto-corrected {rep.old_value} -> {rep.new_value}: {rep.reason}"
            )

    overall_confidence = result.overall_confidence
    has_warnings = bool(field_warnings) or validation.needs_review

    prediction_meta = {
        "overall_confidence": overall_confidence,
        "field_warnings": field_warnings,
        "has_warnings": has_warnings,
    }

    return {
        "date": image_date,
        "course_name": None,
        "tee_set": None,
        "is_team_round": False,
        "players": players,
        "hole_pars": hole_pars,
        "stroke_indexes": stroke_indexes,
        "scorecard_grid": scorecard_grid,
        "predicted_mapping": mapping,
        "prediction_meta": prediction_meta,
        "repaired_cells": [
            {"row": r.row, "col": r.col, "old": r.old_value, "new": r.new_value, "reason": r.reason}
            for r in (validation.repairs if validation else [])
        ],
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_v2_scorecard(
    image_bytes: bytes,
    word_boxes: List[WordBox],
    raw_text: Optional[str] = None,
    image_date: Optional[date] = None,
    is_warped: bool = False,
    debug: bool = False,
) -> dict:
    """Run the full v2 scorecard parse pipeline.

    Parameters
    ----------
    image_bytes : JPEG/PNG image of the scorecard (possibly already warped).
    word_boxes  : Vision OCR word boxes for this image.
    raw_text    : Full OCR text (optional, for fallback).
    image_date  : Date hint (from EXIF or user).
    is_warped   : If True, skip panel detection (image is already cropped).
    debug       : If True, include debug layout data in the response.

    Returns
    -------
    A dict matching the ``DraftRound`` shape, plus optional ``debug_layout``.
    """
    tokens = wordboxes_to_tokens(word_boxes)

    # 1. Panel detection / normalisation
    normalised_bytes, panel_detected, panel_confidence = detect_and_normalise(
        image_bytes, tokens, skip_if_warped=is_warped,
    )

    # 2. Grid reconstruction
    geometry = reconstruct_grid(normalised_bytes, tokens)

    # 3. Token-to-cell assignment
    cell_values = assign_tokens(tokens, geometry)

    # 4. Semantic inference
    if cell_values:
        result = infer_semantics(cell_values)
        result.geometry = geometry
    else:
        result = ParseV2Result(geometry=geometry)

    # 5. Validation + repair
    validation = validate_and_repair(result)
    result.validation = validation

    # 6. Compute overall confidence
    geo_conf = geometry.strategy_confidence if geometry else 0.0
    val_conf = 1.0 if validation.is_consistent else 0.5
    player_conf = min(len(result.player_rows) / 4.0, 1.0) if result.player_rows else 0.0
    result.overall_confidence = 0.3 * panel_confidence + 0.3 * geo_conf + 0.2 * val_conf + 0.2 * player_conf

    # 7. Adapt to DraftRound shape
    draft = _adapt_to_draft_round(result, validation, image_date)

    # 8. Optional debug data
    if debug:
        debug_payload = build_debug_payload(geometry, tokens, validation, cell_values)
        draft["debug_layout"] = debug_payload.model_dump()

    return draft
