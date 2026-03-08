"""Tests for scorecard and stats parsers (simulator OCR: rank 1-4 + any initial, position-based stats)."""
from __future__ import annotations

import unittest

from app.parsers import parse_scorecard_text, parse_stats_text


# Sample raw scorecard: 3 players (1 K, 2 B, 3 and R on two lines), back nine + totals
RAW_SCORECARD_THREE = """SCORECARD > SINGLE LEADERBOARD
B9
NET
GROSS
10
11
12
OUT
TOTAL
1 K
4
5
7
4
4
6
5
4
6
45
45
2 B
6
5
6
4
7
5
5
3
6
47
47
3
R
4
5
7
6
12
5
7
27
7
80
80
PRINT
CONTINUE
DELL"""

# One player only (different initial)
RAW_SCORECARD_ONE = """B9
1 X
4
5
4
4
5
4
5
4
5
38
38"""

# Two players, single-token "2Y" style
RAW_SCORECARD_TWO_SINGLE_TOKEN = """B9
1 A
4
5
4
4
5
4
5
4
5
40
40
2Y
5
5
5
5
5
5
5
5
5
45
45"""

# Four players (cap at 4)
RAW_SCORECARD_FOUR = """B9
1 P
4
4
4
4
4
4
4
4
4
36
36
2 Q
5
5
5
5
5
5
5
5
5
45
45
3 R
5
5
5
5
5
5
5
5
5
45
45
4 S
6
6
6
6
6
6
6
6
6
54
54"""

# Stats text: 3 rows with % and YD (match by position to scorecard players)
RAW_STATS = """SCORECARD > SINGLE LEADERBOARD
B9
1 K
38%
50%
184YD
18
0%
45
45
2 B
29%
11%
232YD
12
0%
100%
47
47
3 R
14%
11%
184YD
15
0%
80
80
PRINT
ROUND STATS
CONTINUE
DELL"""


class TestScorecardParser(unittest.TestCase):
    def test_three_players_rank_plus_initial(self) -> None:
        r = parse_scorecard_text(RAW_SCORECARD_THREE)
        self.assertEqual(len(r.players), 3)
        self.assertEqual(r.players[0].name, "1 K")
        self.assertEqual(r.players[1].name, "2 B")
        self.assertEqual(r.players[2].name, "3 R")
        self.assertEqual(r.players[0].total_score, 45)
        self.assertEqual(r.players[1].total_score, 47)
        self.assertEqual(r.players[2].total_score, 80)
        hole_scores_1 = [hs for hs in r.hole_scores if hs.player_name == "1 K"]
        self.assertEqual(len(hole_scores_1), 9)
        self.assertEqual(hole_scores_1[0].hole_number, 10)
        self.assertEqual(hole_scores_1[0].score, 4)

    def test_one_player_different_initial(self) -> None:
        r = parse_scorecard_text(RAW_SCORECARD_ONE)
        self.assertEqual(len(r.players), 1)
        self.assertEqual(r.players[0].name, "1 X")
        self.assertEqual(r.players[0].total_score, 38)

    def test_two_players_single_token_rank_letter(self) -> None:
        r = parse_scorecard_text(RAW_SCORECARD_TWO_SINGLE_TOKEN)
        self.assertEqual(len(r.players), 2)
        self.assertEqual(r.players[0].name, "1 A")
        self.assertEqual(r.players[1].name, "2 Y")
        self.assertEqual(r.players[0].total_score, 40)
        self.assertEqual(r.players[1].total_score, 45)

    def test_four_players_cap(self) -> None:
        r = parse_scorecard_text(RAW_SCORECARD_FOUR)
        self.assertEqual(len(r.players), 4)
        self.assertEqual(r.players[0].name, "1 P")
        self.assertEqual(r.players[3].name, "4 S")
        self.assertEqual(r.players[3].total_score, 54)

    def test_rank_5_ignored_no_extra_player(self) -> None:
        # Par row "3 4 4 3 5" should not start a player (5 is not rank 1-4)
        text = """OUT
TOTAL
3
4
4
3
5
36 36
1 K
4
5
7
4
4
6
5
4
6
45
45"""
        r = parse_scorecard_text(text)
        self.assertEqual(len(r.players), 1)
        self.assertEqual(r.players[0].name, "1 K")


class TestStatsParserPositionBased(unittest.TestCase):
    def test_stats_merge_by_position(self) -> None:
        scorecard_round = parse_scorecard_text(RAW_SCORECARD_THREE)
        self.assertEqual(len(scorecard_round.players), 3)
        merged = parse_stats_text(RAW_STATS, existing_round=scorecard_round)
        # Position 0 (1 K) gets first stats row
        p0 = merged.players[0]
        self.assertEqual(p0.fairways_hit, 38)
        self.assertEqual(p0.fairways_possible, 100)
        self.assertEqual(p0.gir, 50)
        self.assertEqual(p0.gir_possible, 100)
        self.assertEqual(p0.avg_drive_distance, 184.0)
        self.assertEqual(p0.total_putts, 18)
        self.assertEqual(p0.scramble_successes, 0)
        self.assertEqual(p0.scramble_opportunities, 100)
        # Position 1 (2 B)
        p1 = merged.players[1]
        self.assertEqual(p1.fairways_hit, 29)
        self.assertEqual(p1.avg_drive_distance, 232.0)
        self.assertEqual(p1.total_putts, 12)
        self.assertEqual(p1.sand_save_successes, 100)
        self.assertEqual(p1.sand_save_opportunities, 100)
        # Position 2 (3 R)
        p2 = merged.players[2]
        self.assertEqual(p2.fairways_hit, 14)
        self.assertEqual(p2.gir, 11)
        self.assertEqual(p2.avg_drive_distance, 184.0)
        self.assertEqual(p2.total_putts, 15)
        self.assertEqual(p2.total_score, 80)

    def test_stats_different_initials_still_match_by_position(self) -> None:
        # Scorecard has 1 A, 2 Y; stats have 1 K, 2 B - match by rank only
        scorecard_text = """B9
1 A
4
5
4
4
5
4
5
4
5
40
40
2 Y
5
5
5
5
5
5
5
5
5
45
45"""
        stats_text = """1 K
38%
50%
184YD
18
2 B
29%
232YD
12
PRINT"""
        scorecard_round = parse_scorecard_text(scorecard_text)
        merged = parse_stats_text(stats_text, existing_round=scorecard_round)
        self.assertEqual(merged.players[0].name, "1 A")
        self.assertEqual(merged.players[0].fairways_hit, 38)
        self.assertEqual(merged.players[0].avg_drive_distance, 184.0)
        self.assertEqual(merged.players[1].name, "2 Y")
        self.assertEqual(merged.players[1].fairways_hit, 29)
        self.assertEqual(merged.players[1].avg_drive_distance, 232.0)


if __name__ == "__main__":
    unittest.main()
