"""Tests for the grid prediction engine."""
from __future__ import annotations

import unittest

from app.grid import ScorecardGrid, text_to_grid, clean_grid
from app.grid_predictor import (
    predict_scorecard_mapping,
    predict_stats,
    PredictionResult,
    StatsPrediction,
)


PAPER_SCORECARD_TEXT = """\
Hole 1 2 3 4 5 6 7 8 9 OUT 10 11 12 13 14 15 16 17 18 IN TOTAL
Alice 4 4 3 5 4 4 3 5 4 36 4 5 4 4 3 5 4 4 5 38 74
Bob 5 5 4 4 5 5 4 5 5 42 5 5 5 4 4 5 5 4 5 42 84"""

SIMULATOR_SCORECARD_TEXT = """\
SCORECARD > SINGLE LEADERBOARD
B9
10 11 12 13 14 15 16 17 18 OUT TOTAL
1 Kevin 4 5 7 4 4 6 5 4 6 45 45
2 John 6 5 6 4 7 5 5 3 6 47 47
3 Rachel 4 5 7 6 12 5 7 27 7 80 80
PRINT
CONTINUE"""

SIMPLE_NO_HEADER = """\
Alice 4 5 3 4 5 3 4 5 3
Bob 5 4 4 5 4 4 5 4 4"""


class TestPredictScorecardMapping(unittest.TestCase):

    def test_paper_scorecard_18_holes(self) -> None:
        grid = text_to_grid(PAPER_SCORECARD_TEXT)
        result = predict_scorecard_mapping(grid)

        self.assertIsInstance(result, PredictionResult)
        self.assertGreater(result.overall_confidence, 0.0)

        m = result.mapping
        self.assertIsNotNone(m.header_row)
        self.assertGreaterEqual(len(m.hole_cols), 9)
        self.assertIsNotNone(m.total_col)

        self.assertEqual(m.first_hole_number, 1)

    def test_simulator_back_nine(self) -> None:
        grid = text_to_grid(SIMULATOR_SCORECARD_TEXT)
        result = predict_scorecard_mapping(grid)

        m = result.mapping
        self.assertIsNotNone(m.header_row)
        self.assertGreaterEqual(len(m.hole_cols), 9)
        self.assertEqual(m.first_hole_number, 10)

    def test_no_header_infers_from_data(self) -> None:
        grid = text_to_grid(SIMPLE_NO_HEADER)
        result = predict_scorecard_mapping(grid)

        m = result.mapping
        self.assertGreater(len(m.hole_cols), 0)

    def test_empty_grid(self) -> None:
        grid = ScorecardGrid(rows=[])
        result = predict_scorecard_mapping(grid)
        self.assertEqual(result.overall_confidence, 0.0)

    def test_prediction_produces_player_names(self) -> None:
        """End-to-end: prediction + apply_grid_mapping yields named players."""
        from app.grid import apply_grid_mapping

        grid = text_to_grid(PAPER_SCORECARD_TEXT)
        result = predict_scorecard_mapping(grid)
        draft = apply_grid_mapping(grid, result.mapping)
        players = draft["players"]

        self.assertGreaterEqual(len(players), 2)
        names = [p["name"] for p in players]
        self.assertIn("Alice", names)
        self.assertIn("Bob", names)

    def test_paper_scorecard_hole_scores(self) -> None:
        """Verify predicted mapping extracts correct scores for a full 18-hole card."""
        from app.grid import apply_grid_mapping

        grid = text_to_grid(PAPER_SCORECARD_TEXT)
        result = predict_scorecard_mapping(grid)
        draft = apply_grid_mapping(grid, result.mapping)
        alice = draft["players"][0]

        self.assertEqual(alice["name"], "Alice")
        scored_holes = [
            hs for hs in alice["hole_scores"] if hs["score"] is not None
        ]
        self.assertEqual(len(scored_holes), 18)
        self.assertEqual(alice["hole_scores"][0]["score"], 4)
        self.assertEqual(alice["hole_scores"][17]["score"], 5)

    def test_constructed_grid_prediction(self) -> None:
        grid = ScorecardGrid(rows=[
            ["Hole", "1", "2", "3", "Total"],
            ["Par", "4", "5", "3", ""],
            ["Alice", "4", "5", "3", "12"],
            ["Bob", "5", "6", "4", "15"],
        ])
        result = predict_scorecard_mapping(grid)
        m = result.mapping

        self.assertEqual(m.header_row, 0)
        self.assertEqual(len(m.hole_cols), 3)
        self.assertIsNotNone(m.total_col)

        from app.grid import apply_grid_mapping
        draft = apply_grid_mapping(grid, m)
        players = draft["players"]
        names = [p["name"] for p in players]
        self.assertIn("Alice", names)
        self.assertIn("Bob", names)
        self.assertNotIn("Par", names)


class TestPredictStats(unittest.TestCase):

    def test_keyword_columns(self) -> None:
        grid = ScorecardGrid(rows=[
            ["Name", "Fairways", "GIR", "Putts", "Drive", "Total"],
            ["Alice", "10/14", "12/18", "32", "235", "74"],
            ["Bob", "8/14", "10/18", "34", "210", "84"],
        ])
        result = predict_stats(grid)

        self.assertIsInstance(result, StatsPrediction)
        self.assertEqual(len(result.player_stats), 2)

        alice = result.player_stats[0]
        self.assertEqual(alice["fairways_hit"], 10)
        self.assertEqual(alice["fairways_possible"], 14)
        self.assertEqual(alice["gir"], 12)
        self.assertEqual(alice["gir_possible"], 18)
        self.assertEqual(alice["total_putts"], 32)
        self.assertEqual(alice["avg_drive_distance"], 235)
        self.assertEqual(alice["total_score"], 74)

    def test_keyword_rows_transposed(self) -> None:
        grid = ScorecardGrid(rows=[
            ["Stat", "Player 1", "Player 2"],
            ["Fairways", "50%", "64%"],
            ["GIR", "33%", "44%"],
            ["Putts", "18", "16"],
        ])
        result = predict_stats(grid)
        self.assertEqual(len(result.player_stats), 2)
        self.assertEqual(result.player_stats[0]["fairways_hit"], 50)
        self.assertEqual(result.player_stats[1]["gir"], 44)
        self.assertEqual(result.player_stats[0]["total_putts"], 18)

    def test_simulator_format(self) -> None:
        grid = ScorecardGrid(rows=[
            ["Round", "Stats"],
            ["1", "K"],
            ["50%", "33%", "0%", "-", "235YD", "18", "45", "45"],
            ["2", "J"],
            ["64%", "44%", "50%", "-", "201YD", "16", "47", "47"],
        ])
        result = predict_stats(grid)
        self.assertEqual(len(result.player_stats), 2)

        k = result.player_stats[0]
        self.assertEqual(k["fairways_hit"], 50)
        self.assertEqual(k["gir"], 33)
        self.assertEqual(k["scramble_successes"], 0)
        self.assertEqual(k["avg_drive_distance"], 235)
        self.assertEqual(k["total_putts"], 18)
        self.assertEqual(k["total_score"], 45)

    def test_empty_grid(self) -> None:
        result = predict_stats(ScorecardGrid(rows=[]))
        self.assertEqual(result.player_stats, [])
        self.assertEqual(result.overall_confidence, 0.0)

    def test_percentage_parsing(self) -> None:
        grid = ScorecardGrid(rows=[
            ["Name", "Fairways", "GIR"],
            ["Alice", "65%", "44%"],
        ])
        result = predict_stats(grid)
        self.assertEqual(len(result.player_stats), 1)
        self.assertEqual(result.player_stats[0]["fairways_hit"], 65)
        self.assertEqual(result.player_stats[0]["fairways_possible"], 100)


if __name__ == "__main__":
    unittest.main()
