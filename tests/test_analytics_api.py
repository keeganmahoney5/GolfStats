from __future__ import annotations

from datetime import date, datetime, timedelta
import unittest

from app.db import HoleScore, Player, Round, RoundPlayer
from app.main import (
    _compute_hole_difficulty,
    _compute_performance_trends,
    _compute_player_ratings,
    _compute_single_player_leaderboards,
    _compute_team_leaderboards,
    _filter_rounds_by_holes,
    _round_avg_si,
    _round_holes_type,
)


def _player_round(
    name: str,
    scores: list[int],
    *,
    total_score: int | None = None,
    team_name: str | None = None,
    fairways_hit: int | None = None,
    fairways_possible: int | None = None,
    gir: int | None = None,
    gir_possible: int | None = None,
    avg_drive_distance: int | None = None,
    total_putts: int | None = None,
    scramble_successes: int | None = None,
    scramble_opportunities: int | None = None,
    sand_save_successes: int | None = None,
    sand_save_opportunities: int | None = None,
) -> RoundPlayer:
    player = Player(name=name)
    round_player = RoundPlayer(
        player=player,
        team_name=team_name,
        total_score=total_score if total_score is not None else sum(scores),
        fairways_hit=fairways_hit,
        fairways_possible=fairways_possible,
        gir=gir,
        gir_possible=gir_possible,
        avg_drive_distance=avg_drive_distance,
        total_putts=total_putts,
        scramble_successes=scramble_successes,
        scramble_opportunities=scramble_opportunities,
        sand_save_successes=sand_save_successes,
        sand_save_opportunities=sand_save_opportunities,
    )
    round_player.hole_scores = [
        HoleScore(hole_number=index + 1, score=score)
        for index, score in enumerate(scores)
    ]
    return round_player


def _round(
    round_id: int,
    round_date: date | None,
    pars: list[int | None],
    stroke_indexes: list[int | None] | None,
    players: list[RoundPlayer],
    *,
    is_team_round: bool = False,
    course_name: str = "Test Course",
) -> Round:
    round_ = Round(
        id=round_id,
        date=round_date,
        course_name=course_name,
        is_team_round=is_team_round,
        hole_pars=pars,
        stroke_indexes=stroke_indexes,
        created_at=datetime(2026, 1, 1) + timedelta(days=round_id),
    )
    round_.round_players = players
    return round_


class TestRoundHolesType(unittest.TestCase):

    def test_round_holes_type_front_9(self) -> None:
        round_ = _round(
            1,
            date(2026, 1, 1),
            [4] * 9 + [None] * 9,
            [1, 2, 3, 4, 5, 6, 7, 8, 9] + [None] * 9,
            [_player_round("Alice", [4] * 9)],
        )
        self.assertEqual(_round_holes_type(round_), 9)

    def test_round_holes_type_back_9(self) -> None:
        rp = _player_round("Alice", [4] * 9)
        rp.hole_scores = [HoleScore(hole_number=h, score=4) for h in range(10, 19)]
        round_ = _round(
            1,
            date(2026, 1, 1),
            [None] * 9 + [4] * 9,
            [None] * 9 + list(range(10, 19)),
            [rp],
        )
        self.assertEqual(_round_holes_type(round_), 9)

    def test_round_holes_type_18(self) -> None:
        round_ = _round(
            1,
            date(2026, 1, 1),
            [4] * 18,
            list(range(1, 19)),
            [_player_round("Alice", [4] * 18)],
        )
        self.assertEqual(_round_holes_type(round_), 18)

    def test_filter_rounds_by_holes(self) -> None:
        round_9 = _round(
            1,
            date(2026, 1, 1),
            [4] * 9 + [None] * 9,
            list(range(1, 10)) + [None] * 9,
            [_player_round("A", [4] * 9)],
        )
        round_18 = _round(
            2,
            date(2026, 1, 2),
            [4] * 18,
            list(range(1, 19)),
            [_player_round("B", [4] * 18)],
        )
        filtered_9 = _filter_rounds_by_holes([round_9, round_18], 9)
        filtered_18 = _filter_rounds_by_holes([round_9, round_18], 18)
        self.assertEqual(len(filtered_9), 1)
        self.assertEqual(filtered_9[0].id, 1)
        self.assertEqual(len(filtered_18), 1)
        self.assertEqual(filtered_18[0].id, 2)


class TestAnalyticsHelpers(unittest.TestCase):

    def test_single_player_leaderboards_are_tie_aware(self) -> None:
        rounds = [
            _round(
                1,
                date(2026, 1, 3),
                [4, 4, 4],
                [1, 2, 3],
                [
                    _player_round("Alice", [3, 4, 5]),
                    _player_round("Bob", [4, 4, 4]),
                ],
            ),
            _round(
                2,
                date(2026, 1, 10),
                [4, 4, 4],
                [4, 5, 6],
                [
                    _player_round("Alice", [6, 4, 3]),
                    _player_round("Bob", [5, 5, 4]),
                ],
            ),
        ]

        result = _compute_single_player_leaderboards(rounds)

        self.assertEqual(result.most_9_hole_round_wins[0].player_name, "Alice")
        self.assertEqual(result.most_9_hole_round_wins[0].count, 2)
        self.assertEqual(result.most_9_hole_round_wins[1].player_name, "Bob")
        self.assertEqual(result.most_9_hole_round_wins[1].count, 1)
        # Worst individual holes ranked by raw score (6 > 5 > 5 > 5 > 4)
        self.assertEqual(result.worst_holes[0].player_name, "Alice")
        self.assertEqual(result.worst_holes[0].score, 6)
        self.assertEqual(result.worst_holes[0].hole_number, 1)
        alice_db = next(e for e in result.double_bogey_plus_per_9 if e.player_name == "Alice")
        self.assertAlmostEqual(alice_db.rate, 1.5)  # 1 db+ in 6 holes = 1.5 per 9
        bob_bogeys = next(e for e in result.bogeys_per_9 if e.player_name == "Bob")
        self.assertAlmostEqual(bob_bogeys.rate, 3.0)  # 2 bogeys in 6 holes
        bob_pars = next(e for e in result.pars_per_9 if e.player_name == "Bob")
        self.assertAlmostEqual(bob_pars.rate, 6.0)  # 4 pars in 6 holes
        alice_birdies = next(e for e in result.birdies_per_9 if e.player_name == "Alice")
        self.assertAlmostEqual(alice_birdies.rate, 3.0)  # 2 birdies in 6 holes

    def test_performance_trends_skip_rounds_without_dates(self) -> None:
        rounds = [
            _round(
                1,
                date(2026, 2, 1),
                [4, 4, 4],
                [1, 5, 9],
                [
                    _player_round("Alice", [4, 3, 4]),
                    _player_round("Bob", [5, 4, 5]),
                ],
            ),
            _round(
                2,
                None,
                [4, 4, 4],
                [2, 6, 10],
                [
                    _player_round("Alice", [3, 4, 4]),
                ],
            ),
        ]

        result = _compute_performance_trends(rounds)

        self.assertEqual(len(result.score_trend_9), 2)
        self.assertEqual(len(result.par_or_better_trend_9), 2)
        alice_point = next(point for point in result.par_or_better_trend_9 if point.player_name == "Alice")
        self.assertEqual(alice_point.par_or_better_count, 3)

    def test_performance_trends_include_avg_si_and_normalized_formula(self) -> None:
        """ScoreTrendPoint has avg_si_of_round; PerformanceTrends has avg_si_of_all_rounds; formula is correct."""
        # Round 1: front 9, SI 1-9 (avg 5), par 36, Alice shoots 38 (+2)
        # Round 2: front 9, SI 10-18 (avg 14), par 36, Alice shoots 40 (+4)
        # avg_si_of_all_rounds_9 = (5 + 14) / 2 = 9.5
        rounds = [
            _round(
                10,
                date(2026, 4, 1),
                [4] * 9 + [None] * 9,
                list(range(1, 10)) + [None] * 9,
                [_player_round("Alice", [4, 5, 4, 5, 4, 4, 5, 4, 3])],
            ),
            _round(
                11,
                date(2026, 4, 2),
                [4] * 9 + [None] * 9,
                [None] * 9 + list(range(10, 19)),
                [_player_round("Alice", [5, 5, 5, 5, 4, 4, 4, 4, 4])],
            ),
        ]
        # Alice front 9: scores sum to 38, par 36, score_to_par=+2
        # Alice back 9: scores sum to 41, par 36, score_to_par=+5
        rp2 = _player_round("Alice", [4] * 9)
        rp2.hole_scores = [HoleScore(hole_number=h, score=4 if h < 14 else 5) for h in range(10, 19)]
        rounds[1].round_players = [rp2]
        rounds[1].hole_pars = [None] * 9 + [4] * 9
        rounds[1].stroke_indexes = [None] * 9 + list(range(10, 19))

        result = _compute_performance_trends(rounds)

        # avg_si_of_all_rounds_9 should be mean of per-round avg: (5 + 14) / 2 = 9.5
        self.assertIsNotNone(result.avg_si_of_all_rounds_9)
        self.assertAlmostEqual(result.avg_si_of_all_rounds_9, 9.5)
        self.assertIsNotNone(result.avg_si_of_all_rounds_18)

        # Score trend 9: two points for Alice
        alice_r1 = next(p for p in result.score_trend_9 if p.round_id == 10 and p.player_name == "Alice")
        alice_r2 = next(p for p in result.score_trend_9 if p.round_id == 11 and p.player_name == "Alice")
        self.assertEqual(alice_r1.avg_si_of_round, 5.0)  # mean of 1-9
        self.assertEqual(alice_r2.avg_si_of_round, 14.0)  # mean of 10-18
        self.assertEqual(alice_r1.score_to_par, 2)
        self.assertEqual(alice_r2.score_to_par, 5)

        # Normalized: score_to_par * (avg_si / avg_si_all)
        # Round 1: 2 * (5/9.5) - tougher course, normalized lower
        # Round 2: 5 * (14/9.5) - easier course, normalized higher
        norm1 = alice_r1.score_to_par * (alice_r1.avg_si_of_round / result.avg_si_of_all_rounds_9)
        norm2 = alice_r2.score_to_par * (alice_r2.avg_si_of_round / result.avg_si_of_all_rounds_9)
        self.assertAlmostEqual(norm1, 2 * (5 / 9.5))
        self.assertAlmostEqual(norm2, 5 * (14 / 9.5))
        self.assertLess(norm1, alice_r1.score_to_par)  # tougher course -> lower normalized
        self.assertGreater(norm2, alice_r2.score_to_par)  # easier course -> higher normalized

    def test_round_avg_si_returns_none_when_no_stroke_indexes(self) -> None:
        round_ = _round(
            12,
            date(2026, 4, 3),
            [4] * 9 + [None] * 9,
            None,  # no stroke indexes
            [_player_round("Alice", [4] * 9)],
        )
        self.assertIsNone(_round_avg_si(round_, 9))

    def test_team_leaderboards_include_best_team_per_round(self) -> None:
        rounds = [
            _round(
                3,
                date(2026, 2, 8),
                [4, 4, 4],
                [1, 2, 3],
                [
                    _player_round("Alice", [3, 4, 4], team_name="Team A"),
                    _player_round("Bob", [4, 4, 4], team_name="Team A"),
                    _player_round("Cara", [3, 3, 3], team_name="Team B"),
                    _player_round("Dan", [4, 3, 3], team_name="Team B"),
                ],
                is_team_round=True,
            ),
            _round(
                4,
                date(2026, 2, 12),
                [4, 4, 4],
                [4, 5, 6],
                [
                    _player_round("Eve", [4, 4, 4], team_name="Blue"),
                    _player_round("Finn", [4, 4, 5], team_name="Blue"),
                    _player_round("Gail", [3, 4, 4], team_name="Red"),
                    _player_round("Hank", [4, 4, 4], team_name="Red"),
                ],
                is_team_round=True,
            ),
        ]

        result = _compute_team_leaderboards(rounds)

        self.assertEqual(len(result.lowest_scores_9), 2)
        self.assertEqual(result.lowest_scores_9[0].team_name, "Team B")
        self.assertEqual(result.lowest_scores_9[0].total_score, 19)
        self.assertEqual(result.lowest_scores_9[1].team_name, "Red")
        self.assertEqual(result.lowest_scores_9[1].total_score, 23)

    def test_hole_difficulty_handles_missing_pars_and_stroke_indexes(self) -> None:
        rounds = [
            _round(
                5,
                date(2026, 3, 1),
                [4, 4, None, 4],
                [1, 6, None, 14],
                [
                    _player_round("Alice", [3, 5, 4, 6]),
                    _player_round("Bob", [4, 4, 4, 5]),
                ],
            ),
        ]

        result = _compute_hole_difficulty(rounds)

        self.assertEqual(len(result.player_score_heatmap), 6)
        alice_si_1 = next(
            entry for entry in result.player_score_heatmap
            if entry.player_name == "Alice" and entry.stroke_index == 1
        )
        self.assertEqual(alice_si_1.average_score_to_par, -1.0)
        self.assertEqual(alice_si_1.rounds_played, 1)
        band_entry = next(
            entry for entry in result.predicted_score_by_stroke_index
            if entry.player_name == "Alice" and entry.band_label == "13-16"
        )
        self.assertEqual(band_entry.average_score_to_par, 2.0)

    def test_player_ratings_work_with_partial_stats(self) -> None:
        rounds = [
            _round(
                6,
                date(2026, 3, 10),
                [4, 4, 4, 4],
                [1, 5, 9, 13],
                [
                    _player_round(
                        "Alice",
                        [4, 4, 4, 4],
                        fairways_hit=3,
                        fairways_possible=4,
                        gir=3,
                        gir_possible=4,
                        avg_drive_distance=260,
                        total_putts=6,
                        scramble_successes=2,
                        scramble_opportunities=3,
                        sand_save_successes=1,
                        sand_save_opportunities=2,
                    ),
                    _player_round(
                        "Bob",
                        [5, 5, 4, 5],
                        fairways_hit=1,
                        fairways_possible=4,
                        gir=1,
                        gir_possible=4,
                        avg_drive_distance=210,
                        total_putts=9,
                    ),
                ],
            ),
            _round(
                7,
                date(2026, 3, 20),
                [4, 4, 4, 4],
                [2, 6, 10, 14],
                [
                    _player_round(
                        "Alice",
                        [4, 3, 4, 4],
                        fairways_hit=2,
                        fairways_possible=4,
                        gir=2,
                        gir_possible=4,
                        avg_drive_distance=250,
                        total_putts=7,
                    ),
                    _player_round(
                        "Cara",
                        [4, 4, 4, 4],
                        total_putts=8,
                    ),
                ],
            ),
        ]

        result = _compute_player_ratings(rounds)

        self.assertEqual(result.players[0].player_name, "Alice")
        alice = next(entry for entry in result.players if entry.player_name == "Alice")
        bob = next(entry for entry in result.players if entry.player_name == "Bob")
        cara = next(entry for entry in result.players if entry.player_name == "Cara")
        self.assertEqual(alice.rounds_played, 2)
        self.assertGreater(alice.driving, bob.driving)
        self.assertGreater(alice.fairway, bob.fairway)
        self.assertGreater(alice.putting, bob.putting)
        self.assertEqual(cara.rounds_played, 1)
        self.assertTrue(0.0 <= cara.short_game <= 100.0)


if __name__ == "__main__":
    unittest.main()
