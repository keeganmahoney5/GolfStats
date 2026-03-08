"""Tests for scorecard v2 constraint validator and repair loop."""
from __future__ import annotations

import unittest
from typing import List

from app.scorecard.models import CellValue, ParseV2Result, ValidationResult
from app.scorecard.validator import (
    CONFUSION_MAP,
    _check_par_sum,
    _check_player_sums,
    _check_score_ranges,
    _confusion_alternatives,
    validate_and_repair,
)


def _make_result(
    grid_text: List[List[str]],
    hole_row: int = 0,
    par_row: int | None = 1,
    si_row: int | None = None,
    player_rows: List[int] | None = None,
    hole_cols: List[int] | None = None,
    out_col: int | None = None,
    in_col: int | None = None,
    total_col: int | None = None,
    name_col: int = 0,
    first_hole_number: int = 1,
) -> ParseV2Result:
    cells: List[List[CellValue]] = []
    for r, row in enumerate(grid_text):
        row_vals = []
        for c, txt in enumerate(row):
            row_vals.append(CellValue(row=r, col=c, best_text=txt, confidence=0.9))
        cells.append(row_vals)

    return ParseV2Result(
        grid_text=grid_text,
        cell_values=cells,
        hole_row=hole_row,
        par_row=par_row,
        si_row=si_row,
        player_rows=player_rows or [],
        hole_cols=hole_cols or [],
        out_col=out_col,
        in_col=in_col,
        total_col=total_col,
        name_col=name_col,
        first_hole_number=first_hole_number,
    )


class TestConfusionAlternatives(unittest.TestCase):

    def test_single_digit(self) -> None:
        alts = _confusion_alternatives("3")
        self.assertIn("8", alts)

    def test_multi_digit(self) -> None:
        alts = _confusion_alternatives("38")
        self.assertIn("88", alts)
        self.assertIn("33", alts)
        self.assertIn("30", alts)

    def test_no_confusion(self) -> None:
        alts = _confusion_alternatives("2")
        self.assertEqual(alts, [])


class TestCheckParSum(unittest.TestCase):

    def test_consistent_par(self) -> None:
        result = _make_result(
            grid_text=[
                ["Hole", "1", "2", "3", "OUT"],
                ["Par", "4", "5", "3", "12"],
                ["Alice", "4", "5", "3", "12"],
            ],
            hole_row=0, par_row=1, player_rows=[2],
            hole_cols=[1, 2, 3], out_col=4,
        )
        violations = _check_par_sum(result)
        self.assertEqual(len(violations), 0)

    def test_inconsistent_par(self) -> None:
        result = _make_result(
            grid_text=[
                ["Hole", "1", "2", "3", "OUT"],
                ["Par", "4", "5", "3", "15"],  # wrong: should be 12
                ["Alice", "4", "5", "3", "12"],
            ],
            hole_row=0, par_row=1, player_rows=[2],
            hole_cols=[1, 2, 3], out_col=4,
        )
        violations = _check_par_sum(result)
        self.assertGreater(len(violations), 0)


class TestCheckPlayerSums(unittest.TestCase):

    def test_consistent_player(self) -> None:
        result = _make_result(
            grid_text=[
                ["Hole", "1", "2", "3", "OUT"],
                ["Par", "4", "5", "3", "12"],
                ["Alice", "4", "5", "3", "12"],
            ],
            hole_row=0, par_row=1, player_rows=[2],
            hole_cols=[1, 2, 3], out_col=4,
        )
        violations = _check_player_sums(result)
        self.assertEqual(len(violations), 0)

    def test_inconsistent_player_out(self) -> None:
        result = _make_result(
            grid_text=[
                ["Hole", "1", "2", "3", "OUT"],
                ["Par", "4", "5", "3", "12"],
                ["Alice", "4", "5", "8", "12"],  # 4+5+8=17 != 12
            ],
            hole_row=0, par_row=1, player_rows=[2],
            hole_cols=[1, 2, 3], out_col=4,
        )
        violations = _check_player_sums(result)
        self.assertGreater(len(violations), 0)


class TestScoreRanges(unittest.TestCase):

    def test_normal_scores(self) -> None:
        result = _make_result(
            grid_text=[
                ["Hole", "1", "2", "3"],
                ["Alice", "4", "5", "3"],
            ],
            hole_row=0, par_row=None, player_rows=[1],
            hole_cols=[1, 2, 3],
        )
        warnings = _check_score_ranges(result)
        self.assertEqual(len(warnings), 0)

    def test_high_score_flagged(self) -> None:
        result = _make_result(
            grid_text=[
                ["Hole", "1", "2", "3"],
                ["Alice", "4", "5", "18"],
            ],
            hole_row=0, par_row=None, player_rows=[1],
            hole_cols=[1, 2, 3],
        )
        warnings = _check_score_ranges(result)
        self.assertGreater(len(warnings), 0)


class TestValidateAndRepair(unittest.TestCase):

    def test_consistent_needs_no_repair(self) -> None:
        result = _make_result(
            grid_text=[
                ["Hole", "1", "2", "3", "OUT"],
                ["Par", "4", "5", "3", "12"],
                ["Alice", "4", "5", "3", "12"],
            ],
            hole_row=0, par_row=1, player_rows=[2],
            hole_cols=[1, 2, 3], out_col=4,
        )
        validation = validate_and_repair(result)
        self.assertTrue(validation.is_consistent)
        self.assertEqual(len(validation.repairs), 0)

    def test_ocr_confusion_repaired(self) -> None:
        """Scenario: OCR reads '8' instead of '3' for one hole score.
        Sum is 4+5+8=17 but OUT shows 12. Repair should fix 8->3."""
        result = _make_result(
            grid_text=[
                ["Hole", "1", "2", "3", "OUT"],
                ["Par", "4", "5", "3", "12"],
                ["Alice", "4", "5", "8", "12"],  # "8" should be "3"
            ],
            hole_row=0, par_row=1, player_rows=[2],
            hole_cols=[1, 2, 3], out_col=4,
        )
        # Lower confidence on the "8" cell to guide repair
        result.cell_values[2][3].confidence = 0.3

        validation = validate_and_repair(result)
        self.assertTrue(validation.is_consistent)
        self.assertGreater(len(validation.repairs), 0)
        repaired_vals = [r.new_value for r in validation.repairs]
        self.assertIn("3", repaired_vals)

    def test_unrepairable_returns_needs_review(self) -> None:
        """When no confusion-map swap fixes the constraint, flag for review."""
        # 2+2+2=6 != 12.  The digits "2" have no confusion alternatives,
        # and no single swap on any cell can bridge a gap of 6.
        result = _make_result(
            grid_text=[
                ["Hole", "1", "2", "3", "OUT"],
                ["Par", "4", "5", "3", "12"],
                ["Alice", "2", "2", "2", "12"],
            ],
            hole_row=0, par_row=1, player_rows=[2],
            hole_cols=[1, 2, 3], out_col=4,
        )
        for c in (1, 2, 3):
            result.cell_values[2][c].confidence = 0.3
        validation = validate_and_repair(result)
        self.assertTrue(validation.needs_review)

    def test_back_nine_indexing(self) -> None:
        """Verify that first_hole_number=10 correctly maps to back-9 checks."""
        result = _make_result(
            grid_text=[
                ["Hole", "10", "11", "12", "OUT"],
                ["Par", "4", "5", "3", "12"],
                ["Alice", "4", "5", "3", "12"],
            ],
            hole_row=0, par_row=1, player_rows=[2],
            hole_cols=[1, 2, 3], out_col=4,
            first_hole_number=10,
        )
        validation = validate_and_repair(result)
        # back-9 holes 10-12 don't get checked against OUT (which is front-9 keyword)
        # so there should be no violation from the OUT column
        self.assertFalse(validation.needs_review)


if __name__ == "__main__":
    unittest.main()
