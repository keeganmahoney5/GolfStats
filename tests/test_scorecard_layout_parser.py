"""Tests for scorecard v2 layout parser: clustering, token assignment, strategy selection."""
from __future__ import annotations

import unittest
from typing import List

from app.scorecard.models import CellRect, CellValue, GridGeometry, OcrToken
from app.scorecard.grid_reconstruction import (
    _cluster_1d,
    _boundaries_from_centres,
    _make_cells,
    textbox_clustering_reconstruction,
    reconstruct_grid,
)
from app.scorecard.token_assignment import assign_tokens
from app.scorecard.semantic_inference import infer_semantics
from app.scorecard.layout_parser import wordboxes_to_tokens, _adapt_to_draft_round
from app.scorecard.validator import ValidationResult
from app.vision_ocr import WordBox


def _token(text: str, x: float, y: float, w: float = 20, h: float = 14) -> OcrToken:
    return OcrToken(
        text=text,
        mid_x=x, mid_y=y,
        min_x=x - w / 2, max_x=x + w / 2,
        min_y=y - h / 2, max_y=y + h / 2,
        confidence=0.95,
    )


# ---------------------------------------------------------------------------
# Clustering tests
# ---------------------------------------------------------------------------

class TestCluster1D(unittest.TestCase):

    def test_basic_clustering(self) -> None:
        values = [10.0, 12.0, 50.0, 52.0, 100.0, 102.0]
        centres = _cluster_1d(values, min_gap=20)
        self.assertEqual(len(centres), 3)
        self.assertAlmostEqual(centres[0], 11.0)
        self.assertAlmostEqual(centres[1], 51.0)
        self.assertAlmostEqual(centres[2], 101.0)

    def test_single_cluster(self) -> None:
        centres = _cluster_1d([5.0, 6.0, 7.0], min_gap=10)
        self.assertEqual(len(centres), 1)

    def test_empty(self) -> None:
        self.assertEqual(_cluster_1d([], 10), [])


class TestBoundaries(unittest.TestCase):

    def test_two_centres(self) -> None:
        bounds = _boundaries_from_centres([50.0, 150.0], margin=10.0)
        self.assertEqual(len(bounds), 3)
        self.assertAlmostEqual(bounds[0], 40.0)
        self.assertAlmostEqual(bounds[1], 100.0)
        self.assertAlmostEqual(bounds[2], 160.0)

    def test_single_centre(self) -> None:
        bounds = _boundaries_from_centres([100.0], margin=20.0)
        self.assertEqual(len(bounds), 2)


class TestMakeCells(unittest.TestCase):

    def test_grid_2x3(self) -> None:
        cols = [0.0, 50.0, 100.0, 150.0]
        rows = [0.0, 30.0, 60.0]
        cells = _make_cells(cols, rows)
        self.assertEqual(len(cells), 6)
        self.assertEqual(cells[0].row, 0)
        self.assertEqual(cells[0].col, 0)
        self.assertEqual(cells[5].row, 1)
        self.assertEqual(cells[5].col, 2)


# ---------------------------------------------------------------------------
# Text-box clustering strategy
# ---------------------------------------------------------------------------

class TestTextboxClustering(unittest.TestCase):

    def _scorecard_tokens(self) -> List[OcrToken]:
        """3-row, 5-col synthetic scorecard layout."""
        return [
            _token("Hole", 40, 20),
            _token("1", 120, 20), _token("2", 200, 20), _token("3", 280, 20),
            _token("Total", 380, 20),
            _token("Alice", 40, 60),
            _token("4", 120, 60), _token("5", 200, 60), _token("3", 280, 60),
            _token("12", 380, 60),
            _token("Bob", 40, 100),
            _token("5", 120, 100), _token("6", 200, 100), _token("4", 280, 100),
            _token("15", 380, 100),
        ]

    def test_clustering_detects_columns_and_rows(self) -> None:
        tokens = self._scorecard_tokens()
        geo = textbox_clustering_reconstruction(tokens, 500, 140)
        self.assertIsNotNone(geo)
        assert geo is not None
        self.assertGreaterEqual(geo.n_cols, 3)
        self.assertGreaterEqual(geo.n_rows, 2)
        self.assertEqual(geo.strategy, "textbox_clustering")
        self.assertGreater(geo.strategy_confidence, 0.0)

    def test_too_few_tokens_returns_none(self) -> None:
        tokens = [_token("A", 10, 10), _token("B", 20, 10)]
        self.assertIsNone(textbox_clustering_reconstruction(tokens))


# ---------------------------------------------------------------------------
# Token assignment
# ---------------------------------------------------------------------------

class TestTokenAssignment(unittest.TestCase):

    def test_tokens_assigned_to_correct_cells(self) -> None:
        geo = GridGeometry(
            col_boundaries=[0, 80, 160, 240],
            row_boundaries=[0, 40, 80],
            cells=_make_cells([0, 80, 160, 240], [0, 40, 80]),
            image_width=240, image_height=80,
            strategy="test", strategy_confidence=1.0,
        )
        tokens = [
            _token("A", 40, 20),   # row 0, col 0
            _token("B", 120, 20),  # row 0, col 1
            _token("C", 200, 20),  # row 0, col 2
            _token("D", 40, 60),   # row 1, col 0
            _token("E", 120, 60),  # row 1, col 1
        ]
        cells = assign_tokens(tokens, geo)
        self.assertEqual(len(cells), 2)
        self.assertEqual(len(cells[0]), 3)
        self.assertEqual(cells[0][0].best_text, "A")
        self.assertEqual(cells[0][1].best_text, "B")
        self.assertEqual(cells[0][2].best_text, "C")
        self.assertEqual(cells[1][0].best_text, "D")
        self.assertEqual(cells[1][1].best_text, "E")
        self.assertEqual(cells[1][2].best_text, "")


# ---------------------------------------------------------------------------
# Semantic inference (end-to-end on synthetic data)
# ---------------------------------------------------------------------------

class TestSemanticInference(unittest.TestCase):

    def _build_cells(self) -> List[List[CellValue]]:
        """Synthetic 5-row, 6-col scorecard with Hole/Par/Players."""
        data = [
            ["Hole", "1", "2", "3", "OUT", "TOTAL"],
            ["Par", "4", "5", "3", "12", ""],
            ["SI", "7", "3", "5", "", ""],
            ["Alice", "4", "5", "3", "12", "12"],
            ["Bob", "5", "6", "4", "15", "15"],
        ]
        cells: List[List[CellValue]] = []
        for r, row in enumerate(data):
            row_vals: List[CellValue] = []
            for c, txt in enumerate(row):
                row_vals.append(CellValue(row=r, col=c, best_text=txt, confidence=0.9))
            cells.append(row_vals)
        return cells

    def test_identifies_hole_row(self) -> None:
        cells = self._build_cells()
        result = infer_semantics(cells)
        self.assertEqual(result.hole_row, 0)

    def test_identifies_par_and_si(self) -> None:
        cells = self._build_cells()
        result = infer_semantics(cells)
        self.assertEqual(result.par_row, 1)
        self.assertEqual(result.si_row, 2)

    def test_identifies_players(self) -> None:
        cells = self._build_cells()
        result = infer_semantics(cells)
        self.assertIn(3, result.player_rows)
        self.assertIn(4, result.player_rows)
        self.assertNotIn(0, result.player_rows)
        self.assertNotIn(1, result.player_rows)

    def test_identifies_hole_cols(self) -> None:
        cells = self._build_cells()
        result = infer_semantics(cells)
        self.assertEqual(result.hole_cols, [1, 2, 3])

    def test_identifies_out_and_total(self) -> None:
        cells = self._build_cells()
        result = infer_semantics(cells)
        self.assertEqual(result.out_col, 4)
        self.assertEqual(result.total_col, 5)


# ---------------------------------------------------------------------------
# WordBox → OcrToken conversion
# ---------------------------------------------------------------------------

class TestWordBoxConversion(unittest.TestCase):

    def test_basic_conversion(self) -> None:
        boxes = [
            WordBox(text="4", mid_x=100, mid_y=50, min_y=44, max_y=56),
            WordBox(text="Alice", mid_x=50, mid_y=50, min_y=44, max_y=56),
        ]
        tokens = wordboxes_to_tokens(boxes)
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].text, "4")
        self.assertAlmostEqual(tokens[0].mid_x, 100.0)
        self.assertGreater(tokens[0].max_x, tokens[0].min_x)


# ---------------------------------------------------------------------------
# Adapter to DraftRound
# ---------------------------------------------------------------------------

class TestAdaptToDraftRound(unittest.TestCase):

    def test_produces_correct_shape(self) -> None:
        from app.scorecard.models import ParseV2Result
        result = ParseV2Result(
            grid_text=[
                ["Hole", "1", "2", "3", "Total"],
                ["Par", "4", "5", "3", ""],
                ["Alice", "4", "5", "3", "12"],
                ["Bob", "5", "6", "4", "15"],
            ],
            hole_row=0,
            par_row=1,
            player_rows=[2, 3],
            hole_cols=[1, 2, 3],
            total_col=4,
            name_col=0,
            first_hole_number=1,
            overall_confidence=0.8,
        )
        validation = ValidationResult(is_consistent=True)
        draft = _adapt_to_draft_round(result, validation)

        self.assertEqual(len(draft["players"]), 2)
        self.assertEqual(draft["players"][0]["name"], "Alice")
        self.assertEqual(draft["players"][0]["stats"]["total_score"], 12)
        self.assertEqual(draft["players"][0]["hole_scores"][0]["score"], 4)
        self.assertEqual(draft["players"][1]["name"], "Bob")
        self.assertEqual(draft["players"][1]["stats"]["total_score"], 15)

        pars = draft["hole_pars"]
        self.assertEqual(pars[0], 4)
        self.assertEqual(pars[1], 5)
        self.assertEqual(pars[2], 3)
        self.assertIsNone(pars[3])

        self.assertIn("scorecard_grid", draft)
        self.assertIn("predicted_mapping", draft)
        self.assertIn("prediction_meta", draft)


if __name__ == "__main__":
    unittest.main()
