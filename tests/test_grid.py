"""Tests for grid extraction and mapping logic."""
from __future__ import annotations

import unittest

from app.grid import (
    text_to_grid, word_boxes_to_grid, apply_grid_mapping,
    ScorecardGrid, GridMapping,
    normalize_cell, pad_grid_rows, clean_grid, suggest_par_and_si_rows,
)
from app.vision_ocr import WordBox


SAMPLE_SCORECARD_TEXT = """SCORECARD > SINGLE LEADERBOARD
B9
10 11 12 13 14 15 16 17 18 OUT TOTAL
1 Kevin 4 5 7 4 4 6 5 4 6 45 45
2 John 6 5 6 4 7 5 5 3 6 47 47
3 Rachel 4 5 7 6 12 5 7 27 7 80 80
PRINT
CONTINUE"""

PAPER_SCORECARD_TEXT = """Hole 1 2 3 4 5 6 7 8 9 OUT 10 11 12 13 14 15 16 17 18 IN TOTAL
Alice 4 4 3 5 4 4 3 5 4 36 4 5 4 4 3 5 4 4 5 38 74
Bob 5 5 4 4 5 5 4 5 5 42 5 5 5 4 4 5 5 4 5 42 84"""


class TestTextToGrid(unittest.TestCase):
    def test_basic_grid_extraction(self) -> None:
        grid = text_to_grid(SAMPLE_SCORECARD_TEXT)
        self.assertIsInstance(grid, ScorecardGrid)
        self.assertGreater(len(grid.rows), 0)
        self.assertEqual(grid.rows[0], ["SCORECARD", ">", "SINGLE", "LEADERBOARD"])
        header_row = grid.rows[2]
        self.assertIn("10", header_row)
        self.assertIn("TOTAL", header_row)

    def test_empty_text(self) -> None:
        grid = text_to_grid("")
        self.assertEqual(grid.rows, [])

    def test_whitespace_only(self) -> None:
        grid = text_to_grid("   \n  \n\n")
        self.assertEqual(grid.rows, [])


class TestApplyGridMapping(unittest.TestCase):
    def test_simulator_back_nine(self) -> None:
        grid = text_to_grid(SAMPLE_SCORECARD_TEXT)
        mapping = GridMapping(
            header_row=2,
            name_col=1,
            hole_cols=[2, 3, 4, 5, 6, 7, 8, 9, 10],
            total_col=12,
            first_player_row=3,
            last_player_row=5,
        )
        result = apply_grid_mapping(grid, mapping)
        players = result["players"]
        self.assertEqual(len(players), 3)

        self.assertEqual(players[0]["name"], "Kevin")
        self.assertEqual(players[0]["stats"]["total_score"], 45)
        self.assertEqual(players[0]["hole_scores"][0]["score"], 4)
        self.assertEqual(players[0]["hole_scores"][8]["score"], 6)

        self.assertEqual(players[1]["name"], "John")
        self.assertEqual(players[1]["stats"]["total_score"], 47)

        self.assertEqual(players[2]["name"], "Rachel")
        self.assertEqual(players[2]["stats"]["total_score"], 80)

    def test_paper_scorecard_18_holes(self) -> None:
        grid = text_to_grid(PAPER_SCORECARD_TEXT)
        # Cols: 0=Name, 1-9=holes 1-9, 10=OUT, 11-19=holes 10-18, 20=IN, 21=TOTAL
        hole_cols = list(range(1, 10)) + list(range(11, 20))
        mapping = GridMapping(
            header_row=0,
            name_col=0,
            hole_cols=hole_cols,
            total_col=21,
            first_player_row=1,
            last_player_row=2,
        )
        result = apply_grid_mapping(grid, mapping)
        players = result["players"]
        self.assertEqual(len(players), 2)

        self.assertEqual(players[0]["name"], "Alice")
        self.assertEqual(players[0]["stats"]["total_score"], 74)
        self.assertEqual(len(players[0]["hole_scores"]), 18)
        self.assertEqual(players[0]["hole_scores"][0]["score"], 4)
        self.assertEqual(players[0]["hole_scores"][0]["hole_number"], 1)
        self.assertEqual(players[0]["hole_scores"][17]["hole_number"], 18)
        self.assertEqual(players[0]["hole_scores"][17]["score"], 5)

        self.assertEqual(players[1]["name"], "Bob")
        self.assertEqual(players[1]["stats"]["total_score"], 84)

    def test_no_total_col(self) -> None:
        grid = ScorecardGrid(rows=[
            ["Name", "H1", "H2", "H3"],
            ["Alice", "4", "5", "3"],
        ])
        mapping = GridMapping(
            header_row=0,
            name_col=0,
            hole_cols=[1, 2, 3],
            total_col=None,
            first_player_row=1,
            last_player_row=1,
        )
        result = apply_grid_mapping(grid, mapping)
        players = result["players"]
        self.assertEqual(len(players), 1)
        self.assertEqual(players[0]["name"], "Alice")
        self.assertIsNone(players[0]["stats"]["total_score"])
        self.assertEqual(players[0]["hole_scores"][0]["score"], 4)

    def test_no_header_row(self) -> None:
        grid = ScorecardGrid(rows=[
            ["Alice", "4", "5", "3"],
            ["Bob", "5", "4", "4"],
        ])
        mapping = GridMapping(
            header_row=None,
            name_col=0,
            hole_cols=[1, 2, 3],
            total_col=None,
            first_player_row=0,
            last_player_row=None,
        )
        result = apply_grid_mapping(grid, mapping)
        players = result["players"]
        self.assertEqual(len(players), 2)
        self.assertEqual(players[0]["name"], "Alice")
        self.assertEqual(players[1]["name"], "Bob")

    def test_missing_cells_handled(self) -> None:
        """Columns beyond the row length produce None scores."""
        grid = ScorecardGrid(rows=[
            ["Alice", "4"],
        ])
        mapping = GridMapping(
            name_col=0,
            hole_cols=[1, 2, 3],
            first_player_row=0,
        )
        result = apply_grid_mapping(grid, mapping)
        players = result["players"]
        self.assertEqual(len(players), 1)
        self.assertEqual(players[0]["hole_scores"][0]["score"], 4)
        self.assertIsNone(players[0]["hole_scores"][1]["score"])
        self.assertIsNone(players[0]["hole_scores"][2]["score"])

    def test_skips_header_row_in_player_range(self) -> None:
        grid = ScorecardGrid(rows=[
            ["Name", "H1", "H2"],
            ["Alice", "4", "5"],
        ])
        mapping = GridMapping(
            header_row=0,
            name_col=0,
            hole_cols=[1, 2],
            first_player_row=0,
            last_player_row=1,
        )
        result = apply_grid_mapping(grid, mapping)
        players = result["players"]
        self.assertEqual(len(players), 1)
        self.assertEqual(players[0]["name"], "Alice")


class TestWordBoxesToGrid(unittest.TestCase):
    """Test position-based grid reconstruction from Vision API word boxes."""

    def _make_box(self, text: str, x: float, y: float, height: float = 20) -> WordBox:
        return WordBox(
            text=text,
            mid_x=x,
            mid_y=y,
            min_y=y - height / 2,
            max_y=y + height / 2,
        )

    def test_simple_scorecard_grid(self) -> None:
        """Simulate a 3-row, 4-column scorecard layout."""
        boxes = [
            # Row 0: header — Hole  1  2  3
            self._make_box("Hole", 50, 100),
            self._make_box("1", 150, 100),
            self._make_box("2", 250, 100),
            self._make_box("3", 350, 100),
            # Row 1: Alice — 4  5  3
            self._make_box("Alice", 50, 140),
            self._make_box("4", 150, 140),
            self._make_box("5", 250, 140),
            self._make_box("3", 350, 140),
            # Row 2: Bob — 5  4  4
            self._make_box("Bob", 50, 180),
            self._make_box("5", 150, 180),
            self._make_box("4", 250, 180),
            self._make_box("4", 350, 180),
        ]
        grid = word_boxes_to_grid(boxes)
        self.assertEqual(len(grid.rows), 3)
        self.assertEqual(len(grid.rows[0]), 4)
        self.assertEqual(grid.rows[0][0], "Hole")
        self.assertEqual(grid.rows[0][1], "1")
        self.assertEqual(grid.rows[1][0], "Alice")
        self.assertEqual(grid.rows[1][1], "4")
        self.assertEqual(grid.rows[2][0], "Bob")
        self.assertEqual(grid.rows[2][3], "4")

    def test_empty_boxes(self) -> None:
        grid = word_boxes_to_grid([])
        self.assertEqual(grid.rows, [])

    def test_single_row(self) -> None:
        boxes = [
            self._make_box("A", 50, 100),
            self._make_box("B", 150, 102),
            self._make_box("C", 250, 98),
        ]
        grid = word_boxes_to_grid(boxes)
        self.assertEqual(len(grid.rows), 1)
        self.assertEqual(grid.rows[0], ["A", "B", "C"])

    def test_simulator_layout(self) -> None:
        """Simulate the real scorecard: Hole row, SI row, Par row, then players."""
        boxes = [
            # Header row
            self._make_box("#", 30, 50),
            self._make_box("Name", 100, 50),
            self._make_box("1", 180, 50),
            self._make_box("2", 240, 50),
            self._make_box("3", 300, 50),
            self._make_box("Total", 380, 50),
            # SI / Handicap row
            self._make_box("SI", 30, 90),
            self._make_box("", 100, 90),
            self._make_box("7", 180, 90),
            self._make_box("3", 240, 90),
            self._make_box("5", 300, 90),
            # Par row
            self._make_box("Par", 30, 130),
            self._make_box("", 100, 130),
            self._make_box("4", 180, 130),
            self._make_box("5", 240, 130),
            self._make_box("3", 300, 130),
            # Player 1
            self._make_box("1", 30, 170),
            self._make_box("Kevin", 100, 170),
            self._make_box("4", 180, 170),
            self._make_box("5", 240, 170),
            self._make_box("3", 300, 170),
            self._make_box("12", 380, 170),
            # Player 2
            self._make_box("2", 30, 210),
            self._make_box("John", 100, 210),
            self._make_box("5", 180, 210),
            self._make_box("6", 240, 210),
            self._make_box("4", 300, 210),
            self._make_box("15", 380, 210),
        ]
        grid = word_boxes_to_grid(boxes)
        self.assertEqual(len(grid.rows), 5)

        self.assertIn("Name", grid.rows[0])
        self.assertIn("Kevin", grid.rows[3])
        self.assertIn("John", grid.rows[4])


    def test_swapped_axes_auto_corrects(self) -> None:
        """
        Simulate a rotated scorecard where visual rows run along X and
        visual columns run along Y (decreasing).  The auto-detection should
        swap axes, reverse columns, and produce a correctly oriented grid.
        """
        boxes = [
            # Visual row 0 (header) at X=140 — smallest X = first row
            # Columns run along Y *decreasing*: Name(Y=410) H1(330) H2(260) H3(190) Total(50)
            self._make_box("Hole", 140, 410),
            self._make_box("1", 140, 330),
            self._make_box("2", 140, 260),
            self._make_box("3", 140, 190),
            self._make_box("Total", 140, 50),
            # Visual row 1 (player 1) at X=220
            self._make_box("Alice", 220, 410),
            self._make_box("4", 220, 330),
            self._make_box("5", 220, 260),
            self._make_box("3", 220, 190),
            self._make_box("12", 220, 50),
            # Visual row 2 (player 2) at X=300
            self._make_box("Bob", 300, 410),
            self._make_box("5", 300, 330),
            self._make_box("4", 300, 260),
            self._make_box("4", 300, 190),
            self._make_box("18", 300, 50),
        ]
        grid = word_boxes_to_grid(boxes)
        self.assertEqual(len(grid.rows), 3, f"Expected 3 rows, got {len(grid.rows)}")
        max_cols = max(len(r) for r in grid.rows)
        self.assertEqual(max_cols, 5, f"Expected 5 columns, got {max_cols}")

        self.assertEqual(grid.rows[0][0], "Hole")
        self.assertEqual(grid.rows[0][-1], "Total")
        self.assertEqual(grid.rows[1][0], "Alice")
        self.assertEqual(grid.rows[2][0], "Bob")


class TestNormalizationHelpers(unittest.TestCase):

    def test_normalize_cell_strips_pipes(self) -> None:
        self.assertEqual(normalize_cell("|4|"), "4")

    def test_normalize_cell_strips_quotes(self) -> None:
        self.assertEqual(normalize_cell("'Alice'"), "Alice")

    def test_normalize_cell_whitespace(self) -> None:
        self.assertEqual(normalize_cell("  Bob  "), "Bob")

    def test_pad_grid_rows(self) -> None:
        grid = ScorecardGrid(rows=[["a", "b"], ["c"]])
        padded = pad_grid_rows(grid)
        self.assertEqual(padded.rows, [["a", "b"], ["c", ""]])

    def test_clean_grid_removes_empty_rows(self) -> None:
        grid = ScorecardGrid(rows=[["a"], ["", ""], ["b"]])
        cleaned = clean_grid(grid)
        self.assertEqual(len(cleaned.rows), 2)
        self.assertEqual(cleaned.rows[0][0], "a")
        self.assertEqual(cleaned.rows[1][0], "b")

    def test_clean_grid_pads(self) -> None:
        grid = ScorecardGrid(rows=[["a", "b", "c"], ["x"]])
        cleaned = clean_grid(grid)
        self.assertEqual(len(cleaned.rows[1]), 3)


class TestFirstHoleNumber(unittest.TestCase):

    def test_default_first_hole_number(self) -> None:
        """Default first_hole_number=1 preserves backward compatibility."""
        grid = ScorecardGrid(rows=[
            ["Name", "H1", "H2", "H3"],
            ["Alice", "4", "5", "3"],
        ])
        mapping = GridMapping(
            header_row=0,
            name_col=0,
            hole_cols=[1, 2, 3],
            first_player_row=1,
        )
        result = apply_grid_mapping(grid, mapping)
        hs = result["players"][0]["hole_scores"]
        self.assertEqual(hs[0]["hole_number"], 1)
        self.assertEqual(hs[0]["score"], 4)
        self.assertEqual(hs[2]["hole_number"], 3)
        self.assertEqual(hs[2]["score"], 3)
        self.assertIsNone(hs[3]["score"])

    def test_back_nine_first_hole_number(self) -> None:
        grid = ScorecardGrid(rows=[
            ["Name", "10", "11", "12"],
            ["Alice", "4", "5", "3"],
        ])
        mapping = GridMapping(
            header_row=0,
            name_col=0,
            hole_cols=[1, 2, 3],
            first_player_row=1,
            first_hole_number=10,
        )
        result = apply_grid_mapping(grid, mapping)
        hs = result["players"][0]["hole_scores"]
        self.assertIsNone(hs[0]["score"])
        self.assertEqual(hs[9]["hole_number"], 10)
        self.assertEqual(hs[9]["score"], 4)
        self.assertEqual(hs[11]["hole_number"], 12)
        self.assertEqual(hs[11]["score"], 3)

    def test_sparse_layout_with_noise(self) -> None:
        """Grid with extra UI text rows that should be skipped by prediction."""
        boxes = [
            WordBox(text="SCORECARD", mid_x=200, mid_y=20, min_y=10, max_y=30),
            WordBox(text="Hole", mid_x=50, mid_y=60, min_y=50, max_y=70),
            WordBox(text="1", mid_x=150, mid_y=60, min_y=50, max_y=70),
            WordBox(text="2", mid_x=250, mid_y=60, min_y=50, max_y=70),
            WordBox(text="Total", mid_x=350, mid_y=60, min_y=50, max_y=70),
            WordBox(text="Alice", mid_x=50, mid_y=100, min_y=90, max_y=110),
            WordBox(text="4", mid_x=150, mid_y=100, min_y=90, max_y=110),
            WordBox(text="5", mid_x=250, mid_y=100, min_y=90, max_y=110),
            WordBox(text="9", mid_x=350, mid_y=100, min_y=90, max_y=110),
        ]
        grid = word_boxes_to_grid(boxes)
        self.assertGreater(len(grid.rows), 0)

    def test_par_and_stroke_index_rows(self) -> None:
        """When par_row and stroke_index_row are set, hole_pars and stroke_indexes are filled."""
        grid = ScorecardGrid(rows=[
            ["Hole", "1", "2", "3", "Total"],
            ["Par", "4", "5", "3", ""],
            ["SI", "7", "3", "11", ""],
            ["Alice", "4", "5", "3", "12"],
        ])
        mapping = GridMapping(
            header_row=0,
            name_col=0,
            hole_cols=[1, 2, 3],
            total_col=4,
            first_player_row=3,
            last_player_row=3,
            par_row=1,
            stroke_index_row=2,
        )
        result = apply_grid_mapping(grid, mapping)
        self.assertEqual(result["hole_pars"][0], 4)
        self.assertEqual(result["hole_pars"][1], 5)
        self.assertEqual(result["hole_pars"][2], 3)
        self.assertEqual(result["stroke_indexes"][0], 7)
        self.assertEqual(result["stroke_indexes"][1], 3)
        self.assertEqual(result["stroke_indexes"][2], 11)
        self.assertEqual(len(result["players"]), 1)
        self.assertEqual(result["players"][0]["name"], "Alice")

    def test_suggest_par_and_si_rows(self) -> None:
        """Heuristic suggests par row (3-5) and SI row (1-18)."""
        grid = ScorecardGrid(rows=[
            ["Hole", "1", "2", "3", "4", "5", "Total"],
            ["Par", "4", "4", "3", "5", "4", ""],
            ["SI", "7", "3", "11", "1", "9", ""],
            ["Alice", "4", "5", "3", "5", "4", "21"],
        ])
        mapping = GridMapping(
            header_row=0,
            hole_cols=[1, 2, 3, 4, 5],
            first_player_row=3,
        )
        par_row, si_row = suggest_par_and_si_rows(grid, mapping)
        self.assertEqual(par_row, 1)
        self.assertEqual(si_row, 2)


if __name__ == "__main__":
    unittest.main()
