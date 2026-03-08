from dotenv import load_dotenv
load_dotenv(override=True)

import json
from collections import defaultdict
from datetime import date, datetime
from typing import Annotated, Dict, List, Literal, Optional, Tuple

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, BeforeValidator

from sqlalchemy.orm import joinedload

from .db import init_db, SessionLocal, Round, RoundPlayer, Player, HoleScore


def _parse_optional_date(v: object) -> Optional[date]:
    """Accept None, empty string, date, or 'YYYY-MM-DD' string for API request body."""
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        return date.fromisoformat(s)
    raise ValueError(f"Invalid date: {v!r}")


OptionalDate = Annotated[Optional[date], BeforeValidator(_parse_optional_date)]

from .grid import (
    ScorecardGrid, GridMapping, MapGridRequest,
    text_to_grid, word_boxes_to_grid, apply_grid_mapping,
)
from .grid_predictor import predict_stats
from .image_date import get_image_date
from .image_preprocess import auto_detect_corners, perspective_warp
from .vision_ocr import extract_word_boxes
from .scorecard.layout_parser import parse_v2_scorecard


class HoleScoreDraft(BaseModel):
    hole_number: int
    score: Optional[int] = None


class PlayerStatsDraft(BaseModel):
    total_score: Optional[int] = None
    out_score: Optional[int] = None
    in_score: Optional[int] = None
    fairways_hit: Optional[int] = None
    fairways_possible: Optional[int] = None
    gir: Optional[int] = None
    gir_possible: Optional[int] = None
    avg_drive_distance: Optional[int] = None
    total_putts: Optional[int] = None
    scramble_successes: Optional[int] = None
    scramble_opportunities: Optional[int] = None
    sand_save_successes: Optional[int] = None
    sand_save_opportunities: Optional[int] = None


class PlayerDraft(BaseModel):
    name: str
    team_name: Optional[str] = None
    hole_scores: List[HoleScoreDraft] = []
    stats: PlayerStatsDraft = PlayerStatsDraft()


class PredictionMeta(BaseModel):
    overall_confidence: float = 1.0
    field_warnings: Dict[str, str] = {}
    has_warnings: bool = False


class DraftRound(BaseModel):
    date: OptionalDate = None
    course_name: Optional[str] = None
    tee_set: Optional[str] = None
    is_team_round: bool = False
    players: List[PlayerDraft] = []
    hole_pars: List[Optional[int]] = []
    stroke_indexes: List[Optional[int]] = []
    raw_scorecard_text: Optional[str] = None
    raw_stats_text: Optional[str] = None
    scorecard_grid: Optional[ScorecardGrid] = None
    stats_grid: Optional[ScorecardGrid] = None
    predicted_mapping: Optional[GridMapping] = None
    prediction_meta: Optional[PredictionMeta] = None
    # When multiple scorecard images are uploaded, one grid/mapping per image (for tabbed mapper)
    scorecard_grids: Optional[List[Optional[ScorecardGrid]]] = None
    predicted_mappings: Optional[List[Optional[GridMapping]]] = None


class RoundSummary(BaseModel):
    id: int
    date: OptionalDate = None
    course_name: Optional[str] = None
    tee_set: Optional[str] = None
    is_team_round: bool = False
    player_names: List[str] = []
    holes_type: Literal[9, 18] = 18


class RoundDetail(BaseModel):
    id: int
    date: OptionalDate = None
    course_name: Optional[str] = None
    tee_set: Optional[str] = None
    is_team_round: bool = False
    players: List[PlayerDraft] = []
    hole_pars: Optional[List[Optional[int]]] = None
    stroke_indexes: Optional[List[Optional[int]]] = None


class PlayerCountLeaderboardEntry(BaseModel):
    player_name: str
    count: int


class PlayerRateLeaderboardEntry(BaseModel):
    player_name: str
    rate: float  # per 9 holes played


class WorstHolesLeaderboardEntry(BaseModel):
    """A single worst hole played - ranked from worst to best by raw score."""
    player_name: str
    score: int
    hole_number: int
    par: Optional[int] = None
    round_date: Optional[date] = None
    course_name: Optional[str] = None


class LowestRoundScoreEntry(BaseModel):
    player_name: str
    best_score_to_par: Optional[int] = None
    best_total_score: Optional[int] = None
    round_id: int
    round_date: Optional[date] = None
    course_name: Optional[str] = None
    round_par: Optional[int] = None


class SinglePlayerLeaderboards(BaseModel):
    lowest_9_hole_round_scores: List[LowestRoundScoreEntry]
    lowest_18_hole_round_scores: List[LowestRoundScoreEntry]
    most_9_hole_round_wins: List[PlayerCountLeaderboardEntry]
    most_18_hole_round_wins: List[PlayerCountLeaderboardEntry]
    worst_holes: List[WorstHolesLeaderboardEntry]
    double_bogey_plus_per_9: List[PlayerRateLeaderboardEntry]
    bogeys_per_9: List[PlayerRateLeaderboardEntry]
    pars_per_9: List[PlayerRateLeaderboardEntry]
    birdies_per_9: List[PlayerRateLeaderboardEntry]
    eagles_per_9: List[PlayerRateLeaderboardEntry]


class ScoreTrendPoint(BaseModel):
    player_name: str
    round_id: int
    round_date: date
    course_name: Optional[str] = None
    total_score: int
    score_to_par: Optional[int] = None
    avg_si_of_round: Optional[float] = None


class ParOrBetterTrendPoint(BaseModel):
    player_name: str
    round_id: int
    round_date: date
    course_name: Optional[str] = None
    par_or_better_count: int


class PerformanceTrends(BaseModel):
    score_trend_9: List[ScoreTrendPoint]
    score_trend_18: List[ScoreTrendPoint]
    par_or_better_trend_9: List[ParOrBetterTrendPoint]
    par_or_better_trend_18: List[ParOrBetterTrendPoint]
    avg_si_of_all_rounds_9: Optional[float] = None
    avg_si_of_all_rounds_18: Optional[float] = None


class TeamLeaderboardEntry(BaseModel):
    team_name: str
    total_score: int
    round_id: int
    round_date: Optional[date] = None
    course_name: Optional[str] = None
    player_names: List[str]


class TeamLeaderboards(BaseModel):
    lowest_scores_9: List[TeamLeaderboardEntry]
    lowest_scores_18: List[TeamLeaderboardEntry]
    lowest_9_hole_round_scores: List[LowestRoundScoreEntry]
    lowest_18_hole_round_scores: List[LowestRoundScoreEntry]
    most_9_hole_round_wins: List[PlayerCountLeaderboardEntry]
    most_18_hole_round_wins: List[PlayerCountLeaderboardEntry]
    worst_holes: List[WorstHolesLeaderboardEntry]
    double_bogey_plus_per_9: List[PlayerRateLeaderboardEntry]
    bogeys_per_9: List[PlayerRateLeaderboardEntry]
    pars_per_9: List[PlayerRateLeaderboardEntry]
    birdies_per_9: List[PlayerRateLeaderboardEntry]
    eagles_per_9: List[PlayerRateLeaderboardEntry]


class PlayerStrokeIndexHeatmapEntry(BaseModel):
    player_name: str
    stroke_index: int
    average_score_to_par: float
    rounds_played: int


class StrokeIndexBandEntry(BaseModel):
    player_name: str
    band_label: str
    average_score_to_par: float
    sample_size: int


class HoleDifficultyAnalysis(BaseModel):
    player_score_heatmap: List[PlayerStrokeIndexHeatmapEntry]
    predicted_score_by_stroke_index: List[StrokeIndexBandEntry]


class PlayerRatingEntry(BaseModel):
    player_name: str
    driving: float
    fairway: float
    short_game: float
    putting: float
    rounds_played: int


class PlayerRatings(BaseModel):
    players: List[PlayerRatingEntry]


def _normalize_player_name(name: str) -> str:
    """Lowercase, strip whitespace for matching purposes."""
    return name.strip().lower()


def _round_par(round_: Round) -> Optional[int]:
    hole_pars = getattr(round_, "hole_pars", None) or []
    valid_pars = [p for p in hole_pars if isinstance(p, int)]
    return sum(valid_pars) if valid_pars else None


def _hole_par(round_: Round, hole_number: int) -> Optional[int]:
    hole_pars = getattr(round_, "hole_pars", None) or []
    idx = hole_number - 1
    if 0 <= idx < len(hole_pars) and isinstance(hole_pars[idx], int):
        return hole_pars[idx]
    return None


def _hole_stroke_index(round_: Round, hole_number: int) -> Optional[int]:
    stroke_indexes = getattr(round_, "stroke_indexes", None) or []
    idx = hole_number - 1
    if 0 <= idx < len(stroke_indexes) and isinstance(stroke_indexes[idx], int):
        return stroke_indexes[idx]
    return None


def _player_name(round_player: RoundPlayer) -> str:
    if round_player.player and round_player.player.name:
        return round_player.player.name
    return f"Player {round_player.player_id}"


def _player_total_score(round_player: RoundPlayer) -> Optional[int]:
    if round_player.total_score is not None:
        return round_player.total_score
    scores = [hs.score for hs in round_player.hole_scores if hs.score is not None]
    return sum(scores) if scores else None


def _round_player_sort_key(round_: Round) -> tuple:
    return (round_.date or date.max, round_.created_at, round_.id)


def _round_holes_type(round_: Round) -> Literal[9, 18]:
    """Return 9 if round is front/back 9 only, else 18."""
    max_holes = 0
    hole_numbers: set[int] = set()
    for rp in round_.round_players:
        scored = [hs.hole_number for hs in rp.hole_scores if hs.score is not None]
        if not scored:
            continue
        max_holes = max(max_holes, len(scored))
        hole_numbers.update(scored)
    if max_holes <= 9 and (all(h <= 9 for h in hole_numbers) or all(h >= 10 for h in hole_numbers)):
        return 9
    return 18


def _round_par_for_holes(round_: Round, holes_type: Literal[9, 18]) -> Optional[int]:
    """Par for the holes actually played. For 9-hole, infer front vs back from first player."""
    hole_pars = getattr(round_, "hole_pars", None) or []
    if holes_type == 18:
        valid = [p for p in hole_pars if isinstance(p, int)]
        return sum(valid) if valid else None
    # 9-hole: find which nine from first player with scores
    for rp in round_.round_players:
        scored = [hs.hole_number for hs in rp.hole_scores if hs.score is not None]
        if not scored:
            continue
        if all(h <= 9 for h in scored):
            return sum(p for i, p in enumerate(hole_pars) if i < 9 and isinstance(p, int)) or None
        if all(h >= 10 for h in scored):
            return sum(p for i, p in enumerate(hole_pars) if 9 <= i < 18 and isinstance(p, int)) or None
    return None


def _round_avg_si(round_: Round, holes_type: Literal[9, 18]) -> Optional[float]:
    """Average stroke index for holes played. Front 9: indices 0-8, back 9: 9-17, 18: 0-17."""
    stroke_indexes = getattr(round_, "stroke_indexes", None) or []
    if holes_type == 18:
        indices = list(range(18))
    else:
        indices = None
        for rp in round_.round_players:
            scored = [hs.hole_number for hs in rp.hole_scores if hs.score is not None]
            if not scored:
                continue
            if all(h <= 9 for h in scored):
                indices = list(range(9))
                break
            if all(h >= 10 for h in scored):
                indices = list(range(9, 18))
                break
        if indices is None:
            return None
    values = []
    for i in indices:
        if 0 <= i < len(stroke_indexes) and isinstance(stroke_indexes[i], int):
            values.append(stroke_indexes[i])
    return sum(values) / len(values) if values else None


def _filter_rounds_by_holes(rounds: List[Round], holes: Literal[9, 18]) -> List[Round]:
    return [r for r in rounds if _round_holes_type(r) == holes]


def _stroke_index_band_label(stroke_index: Optional[int]) -> Optional[str]:
    if stroke_index is None:
        return None
    if 1 <= stroke_index <= 4:
        return "1-4"
    if 5 <= stroke_index <= 8:
        return "5-8"
    if 9 <= stroke_index <= 12:
        return "9-12"
    if 13 <= stroke_index <= 16:
        return "13-16"
    return None


def _ratio(numerator: Optional[int], denominator: Optional[int]) -> Optional[float]:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _weighted_score(parts: List[Tuple[Optional[float], float]], default: float = 50.0) -> float:
    weighted_total = 0.0
    weight_total = 0.0
    for value, weight in parts:
        if value is None:
            continue
        weighted_total += value * weight
        weight_total += weight
    if weight_total == 0:
        return default
    return weighted_total / weight_total


def _load_all_rounds(session: SessionLocal) -> List[Round]:
    return session.query(Round).order_by(Round.date.asc(), Round.created_at.asc(), Round.id.asc()).all()


def _load_all_rounds_with_relations(session: SessionLocal) -> List[Round]:
    """Load all rounds with round_players, hole_scores, and player eagerly loaded."""
    return (
        session.query(Round)
        .options(
            joinedload(Round.round_players).joinedload(RoundPlayer.hole_scores),
            joinedload(Round.round_players).joinedload(RoundPlayer.player),
        )
        .order_by(Round.date.asc(), Round.created_at.asc(), Round.id.asc())
        .all()
    )


def _round_to_summary(r: Round) -> RoundSummary:
    player_names = [rp.player.name for rp in sorted(r.round_players, key=lambda x: x.id) if rp.player]
    return RoundSummary(
        id=r.id,
        date=r.date,
        course_name=r.course_name,
        tee_set=r.tee_set,
        is_team_round=r.is_team_round,
        player_names=player_names,
        holes_type=_round_holes_type(r),
    )


def _round_to_detail(r: Round) -> RoundDetail:
    players_draft: List[PlayerDraft] = []
    for rp in sorted(r.round_players, key=lambda x: x.id):
        scores_by_hole = {hs.hole_number: hs.score for hs in rp.hole_scores}
        hole_scores = [
            HoleScoreDraft(hole_number=h, score=scores_by_hole.get(h))
            for h in range(1, 19)
        ]
        stats = PlayerStatsDraft(
            total_score=rp.total_score,
            out_score=rp.out_score,
            in_score=rp.in_score,
            fairways_hit=rp.fairways_hit,
            fairways_possible=rp.fairways_possible,
            gir=rp.gir,
            gir_possible=rp.gir_possible,
            avg_drive_distance=rp.avg_drive_distance,
            total_putts=rp.total_putts,
            scramble_successes=rp.scramble_successes,
            scramble_opportunities=rp.scramble_opportunities,
            sand_save_successes=rp.sand_save_successes,
            sand_save_opportunities=rp.sand_save_opportunities,
        )
        players_draft.append(
            PlayerDraft(
                name=rp.player.name,
                team_name=rp.team_name,
                hole_scores=hole_scores,
                stats=stats,
            )
        )
    return RoundDetail(
        id=r.id,
        date=r.date,
        course_name=r.course_name,
        tee_set=r.tee_set,
        is_team_round=r.is_team_round,
        players=players_draft,
        hole_pars=getattr(r, "hole_pars", None),
        stroke_indexes=getattr(r, "stroke_indexes", None),
    )


LOWEST_ROUNDS_TOP_N = 5


def _compute_lowest_round_scores(rounds: List[Round], holes_type: Literal[9, 18]) -> List[LowestRoundScoreEntry]:
    """Top N best individual rounds played, ranked from best to worst."""
    all_rounds: List[Dict[str, object]] = []
    for round_ in rounds:
        round_par = _round_par_for_holes(round_, holes_type)
        for round_player in round_.round_players:
            total = _player_total_score(round_player)
            if total is None:
                continue

            score_to_par = total - round_par if round_par is not None else None
            sort_key = score_to_par if score_to_par is not None else total
            player_name = _player_name(round_player)

            all_rounds.append({
                "player_name": player_name,
                "best_score_to_par": score_to_par,
                "best_total_score": total,
                "round_id": round_.id,
                "round_date": round_.date,
                "course_name": round_.course_name,
                "round_par": round_par,
                "sort_key": sort_key,
            })

    all_rounds.sort(key=lambda item: (item["sort_key"], str(item["player_name"]).lower()))
    return [
        LowestRoundScoreEntry(
            player_name=str(entry["player_name"]),
            best_score_to_par=entry["best_score_to_par"],
            best_total_score=entry["best_total_score"],
            round_id=int(entry["round_id"]),
            round_date=entry["round_date"],
            course_name=entry["course_name"],
            round_par=entry["round_par"],
        )
        for entry in all_rounds[:LOWEST_ROUNDS_TOP_N]
    ]


def _sorted_count_entries(counts: Dict[str, int], names: Dict[str, str]) -> List[PlayerCountLeaderboardEntry]:
    entries = [
        PlayerCountLeaderboardEntry(player_name=names[key], count=counts.get(key, 0))
        for key in names
    ]
    return sorted(entries, key=lambda entry: (-entry.count, entry.player_name.lower()))


def _sorted_rate_entries(
    rates: Dict[str, float],
    names: Dict[str, str],
    ascending: bool = False,
) -> List[PlayerRateLeaderboardEntry]:
    """Sort by rate. ascending=True for bad stats (double_bogey+, bogeys), False for good (pars, birdies, eagles)."""
    entries = [
        PlayerRateLeaderboardEntry(player_name=names[key], rate=round(rates.get(key, 0.0), 2))
        for key in names
    ]
    if ascending:
        return sorted(entries, key=lambda e: (e.rate, e.player_name.lower()))
    return sorted(entries, key=lambda e: (-e.rate, e.player_name.lower()))


WORST_HOLES_TOP_N = 5


def _compute_rate_leaderboards(
    rounds: List[Round],
    names: Dict[str, str],
) -> Tuple[
    Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float],
]:
    """Compute per-9-holes rates for double_bogey+, bogeys, pars, birdies, eagles."""
    double_bogey_plus: Dict[str, int] = defaultdict(int)
    bogeys: Dict[str, int] = defaultdict(int)
    pars: Dict[str, int] = defaultdict(int)
    birdies: Dict[str, int] = defaultdict(int)
    eagles: Dict[str, int] = defaultdict(int)
    holes_played: Dict[str, int] = defaultdict(int)

    for round_ in rounds:
        for round_player in round_.round_players:
            player_key = _normalize_player_name(_player_name(round_player))
            names.setdefault(player_key, _player_name(round_player))

            scored = [hs for hs in round_player.hole_scores if hs.score is not None]
            holes_played[player_key] += len(scored)

            for hole_score in scored:
                par = _hole_par(round_, hole_score.hole_number)
                if par is None:
                    continue
                score_to_par = hole_score.score - par
                if score_to_par >= 2:
                    double_bogey_plus[player_key] += 1
                elif score_to_par == 1:
                    bogeys[player_key] += 1
                elif score_to_par == 0:
                    pars[player_key] += 1
                elif score_to_par == -1:
                    birdies[player_key] += 1
                elif score_to_par <= -2:
                    eagles[player_key] += 1

    def rate(counts: Dict[str, int]) -> Dict[str, float]:
        return {
            k: (counts[k] * 9.0 / holes_played[k]) if holes_played.get(k, 0) > 0 else 0.0
            for k in names
        }

    return (
        rate(double_bogey_plus),
        rate(bogeys),
        rate(pars),
        rate(birdies),
        rate(eagles),
    )


def _compute_single_player_leaderboards(rounds: List[Round]) -> SinglePlayerLeaderboards:
    names: Dict[str, str] = {}
    individual_worst_holes: List[Tuple[str, int, int, Optional[int], Optional[date], Optional[str]]] = []
    wins_9: Dict[str, int] = defaultdict(int)
    wins_18: Dict[str, int] = defaultdict(int)

    for round_ in rounds:
        for round_player in round_.round_players:
            player_name = _player_name(round_player)
            player_key = _normalize_player_name(player_name)
            names.setdefault(player_key, player_name)

            for hole_score in round_player.hole_scores:
                if hole_score.score is None:
                    continue
                par = _hole_par(round_, hole_score.hole_number)
                individual_worst_holes.append((
                    player_name,
                    hole_score.score,
                    hole_score.hole_number,
                    par,
                    round_.date,
                    round_.course_name,
                ))

    for round_ in rounds:
        holes_type = _round_holes_type(round_)
        round_scores: List[Tuple[str, int]] = []
        for round_player in round_.round_players:
            total_score = _player_total_score(round_player)
            if total_score is not None:
                round_scores.append((_normalize_player_name(_player_name(round_player)), total_score))
        if round_scores:
            best_score = min(score for _, score in round_scores)
            wins = wins_9 if holes_type == 9 else wins_18
            for player_key, score in round_scores:
                if score == best_score:
                    wins[player_key] += 1

    individual_worst_holes.sort(key=lambda x: (-x[1], x[0].lower()))
    worst_entries = [
        WorstHolesLeaderboardEntry(
            player_name=name,
            score=score,
            hole_number=hole_number,
            par=par,
            round_date=round_date,
            course_name=course_name,
        )
        for name, score, hole_number, par, round_date, course_name in individual_worst_holes[:WORST_HOLES_TOP_N]
    ]

    rounds_9 = _filter_rounds_by_holes(rounds, 9)
    rounds_18 = _filter_rounds_by_holes(rounds, 18)

    (
        db9_rates, bogey_rates, par_rates, birdie_rates, eagle_rates,
    ) = _compute_rate_leaderboards(rounds, names)

    return SinglePlayerLeaderboards(
        lowest_9_hole_round_scores=_compute_lowest_round_scores(rounds_9, 9),
        lowest_18_hole_round_scores=_compute_lowest_round_scores(rounds_18, 18),
        most_9_hole_round_wins=_sorted_count_entries(wins_9, names),
        most_18_hole_round_wins=_sorted_count_entries(wins_18, names),
        worst_holes=worst_entries,
        double_bogey_plus_per_9=_sorted_rate_entries(db9_rates, names, ascending=True),
        bogeys_per_9=_sorted_rate_entries(bogey_rates, names, ascending=True),
        pars_per_9=_sorted_rate_entries(par_rates, names, ascending=False),
        birdies_per_9=_sorted_rate_entries(birdie_rates, names, ascending=False),
        eagles_per_9=_sorted_rate_entries(eagle_rates, names, ascending=False),
    )


def _compute_performance_trends_for_holes(
    rounds: List[Round],
    holes_type: Literal[9, 18],
) -> Tuple[List[ScoreTrendPoint], List[ParOrBetterTrendPoint], Optional[float]]:
    score_trend: List[ScoreTrendPoint] = []
    par_or_better_trend: List[ParOrBetterTrendPoint] = []
    round_avg_sis: List[float] = []

    for round_ in sorted(rounds, key=_round_player_sort_key):
        if round_.date is None:
            continue

        round_par = _round_par_for_holes(round_, holes_type)
        round_avg_si = _round_avg_si(round_, holes_type)
        if round_avg_si is not None:
            round_avg_sis.append(round_avg_si)

        for round_player in round_.round_players:
            total_score = _player_total_score(round_player)
            if total_score is None:
                continue

            player_name = _player_name(round_player)
            score_trend.append(
                ScoreTrendPoint(
                    player_name=player_name,
                    round_id=round_.id,
                    round_date=round_.date,
                    course_name=round_.course_name,
                    total_score=total_score,
                    score_to_par=(total_score - round_par) if round_par is not None else None,
                    avg_si_of_round=round_avg_si,
                )
            )

            par_or_better_count = 0
            has_valid_par_hole = False
            for hole_score in round_player.hole_scores:
                if hole_score.score is None:
                    continue
                par = _hole_par(round_, hole_score.hole_number)
                if par is None:
                    continue
                has_valid_par_hole = True
                if hole_score.score <= par:
                    par_or_better_count += 1

            if has_valid_par_hole:
                par_or_better_trend.append(
                    ParOrBetterTrendPoint(
                        player_name=player_name,
                        round_id=round_.id,
                        round_date=round_.date,
                        course_name=round_.course_name,
                        par_or_better_count=par_or_better_count,
                    )
                )

    avg_si_of_all = sum(round_avg_sis) / len(round_avg_sis) if round_avg_sis else None
    return score_trend, par_or_better_trend, avg_si_of_all


def _compute_performance_trends(rounds: List[Round]) -> PerformanceTrends:
    rounds_9 = _filter_rounds_by_holes(rounds, 9)
    rounds_18 = _filter_rounds_by_holes(rounds, 18)
    score_trend_9, par_or_better_trend_9, avg_si_9 = _compute_performance_trends_for_holes(rounds_9, 9)
    score_trend_18, par_or_better_trend_18, avg_si_18 = _compute_performance_trends_for_holes(rounds_18, 18)
    return PerformanceTrends(
        score_trend_9=score_trend_9,
        score_trend_18=score_trend_18,
        par_or_better_trend_9=par_or_better_trend_9,
        par_or_better_trend_18=par_or_better_trend_18,
        avg_si_of_all_rounds_9=avg_si_9,
        avg_si_of_all_rounds_18=avg_si_18,
    )


def _filter_team_rounds(rounds: List[Round]) -> List[Round]:
    return [r for r in rounds if r.is_team_round]


def _compute_team_leaderboards_for_holes(rounds: List[Round]) -> List[TeamLeaderboardEntry]:
    lowest_scores: List[TeamLeaderboardEntry] = []
    for round_ in rounds:
        if not round_.is_team_round:
            continue

        grouped: Dict[str, Dict[str, object]] = {}
        for round_player in round_.round_players:
            team_name = (round_player.team_name or "").strip()
            total_score = _player_total_score(round_player)
            if not team_name or total_score is None:
                continue

            bucket = grouped.setdefault(team_name, {"total_score": 0, "player_names": []})
            bucket["total_score"] = int(bucket["total_score"]) + total_score
            bucket["player_names"].append(_player_name(round_player))

        if len(grouped) < 2:
            continue

        best_total = min(int(bucket["total_score"]) for bucket in grouped.values())
        for team_name, bucket in grouped.items():
            if int(bucket["total_score"]) != best_total:
                continue
            lowest_scores.append(
                TeamLeaderboardEntry(
                    team_name=team_name,
                    total_score=int(bucket["total_score"]),
                    round_id=round_.id,
                    round_date=round_.date,
                    course_name=round_.course_name,
                    player_names=sorted(bucket["player_names"]),
                )
            )

    lowest_scores.sort(key=lambda entry: (entry.total_score, entry.round_date or date.max, entry.team_name.lower()))
    return lowest_scores


def _compute_team_lowest_round_scores(
    rounds: List[Round], holes_type: Literal[9, 18]
) -> List[LowestRoundScoreEntry]:
    """Top N best team rounds (lowest team totals) across all team rounds."""
    all_team_rounds: List[Dict[str, object]] = []
    for round_ in rounds:
        if not round_.is_team_round:
            continue
        round_par = _round_par_for_holes(round_, holes_type)
        grouped: Dict[str, int] = {}
        for round_player in round_.round_players:
            team_name = (round_player.team_name or "").strip()
            total = _player_total_score(round_player)
            if not team_name or total is None:
                continue
            grouped[team_name] = grouped.get(team_name, 0) + total

        for team_name, total_score in grouped.items():
            score_to_par = total_score - round_par if round_par is not None else None
            sort_key = score_to_par if score_to_par is not None else total_score
            all_team_rounds.append({
                "player_name": team_name,
                "best_score_to_par": score_to_par,
                "best_total_score": total_score,
                "round_id": round_.id,
                "round_date": round_.date,
                "course_name": round_.course_name,
                "round_par": round_par,
                "sort_key": sort_key,
            })

    all_team_rounds.sort(key=lambda item: (item["sort_key"], str(item["player_name"]).lower()))
    return [
        LowestRoundScoreEntry(
            player_name=str(entry["player_name"]),
            best_score_to_par=entry["best_score_to_par"],
            best_total_score=entry["best_total_score"],
            round_id=int(entry["round_id"]),
            round_date=entry["round_date"],
            course_name=entry["course_name"],
            round_par=entry["round_par"],
        )
        for entry in all_team_rounds[:LOWEST_ROUNDS_TOP_N]
    ]


def _compute_team_wins_and_rates(
    rounds: List[Round],
) -> Tuple[
    Dict[str, int], Dict[str, int],
    List[Tuple[str, int, int, Optional[int], Optional[date], Optional[str]]],
    Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float],
    Dict[str, str],
]:
    """Compute team wins, worst holes, and rate leaderboards from team rounds. Returns team_names mapping."""
    wins_9: Dict[str, int] = defaultdict(int)
    wins_18: Dict[str, int] = defaultdict(int)
    team_worst_holes: List[Tuple[str, int, int, Optional[int], Optional[date], Optional[str]]] = []
    double_bogey_plus: Dict[str, int] = defaultdict(int)
    bogeys: Dict[str, int] = defaultdict(int)
    pars: Dict[str, int] = defaultdict(int)
    birdies: Dict[str, int] = defaultdict(int)
    eagles: Dict[str, int] = defaultdict(int)
    holes_played: Dict[str, int] = defaultdict(int)
    team_names: Dict[str, str] = {}

    for round_ in rounds:
        if not round_.is_team_round:
            continue
        holes_type = _round_holes_type(round_)
        grouped: Dict[str, Dict[str, object]] = {}
        for round_player in round_.round_players:
            team_name = (round_player.team_name or "").strip()
            if not team_name:
                continue
            team_key = _normalize_player_name(team_name)
            bucket = grouped.setdefault(team_key, {"total_score": 0, "hole_scores": [], "player_names": [], "display_name": team_name})
            team_names.setdefault(team_key, team_name)
            total = _player_total_score(round_player)
            if total is not None:
                bucket["total_score"] = int(bucket["total_score"]) + total
            bucket["player_names"].append(_player_name(round_player))
            for hs in round_player.hole_scores:
                if hs.score is not None:
                    bucket["hole_scores"].append((hs.hole_number, hs.score, _hole_par(round_, hs.hole_number)))

        if len(grouped) < 2:
            continue

        best_total = min(int(b["total_score"]) for b in grouped.values())
        wins = wins_9 if holes_type == 9 else wins_18
        for team_key, bucket in grouped.items():
            if int(bucket["total_score"]) == best_total:
                wins[team_key] += 1

        for team_key, bucket in grouped.items():
            team_name = bucket["display_name"]
            for hole_number, score, par in bucket["hole_scores"]:
                team_worst_holes.append((team_name, score, hole_number, par, round_.date, round_.course_name))
                holes_played[team_key] += 1
                if par is None:
                    continue
                score_to_par = score - par
                if score_to_par >= 2:
                    double_bogey_plus[team_key] += 1
                elif score_to_par == 1:
                    bogeys[team_key] += 1
                elif score_to_par == 0:
                    pars[team_key] += 1
                elif score_to_par == -1:
                    birdies[team_key] += 1
                elif score_to_par <= -2:
                    eagles[team_key] += 1

    team_worst_holes.sort(key=lambda x: (-x[1], x[0].lower()))

    all_keys = set(wins_9) | set(wins_18) | set(double_bogey_plus) | set(bogeys) | set(pars) | set(birdies) | set(eagles)
    for k in all_keys:
        if k not in team_names:
            team_names[k] = k

    def rate(counts: Dict[str, int]) -> Dict[str, float]:
        return {
            k: (counts[k] * 9.0 / holes_played[k]) if holes_played.get(k, 0) > 0 else 0.0
            for k in team_names
        }

    return (
        wins_9, wins_18,
        team_worst_holes[:WORST_HOLES_TOP_N],
        rate(double_bogey_plus), rate(bogeys), rate(pars), rate(birdies), rate(eagles),
        team_names,
    )


def _compute_team_leaderboards(rounds: List[Round]) -> TeamLeaderboards:
    team_rounds = _filter_team_rounds(rounds)
    rounds_9 = _filter_rounds_by_holes(team_rounds, 9)
    rounds_18 = _filter_rounds_by_holes(team_rounds, 18)

    wins_9, wins_18, worst_entries, db9, bogey, par, birdie, eagle, team_names = _compute_team_wins_and_rates(team_rounds)
    worst_list = [
        WorstHolesLeaderboardEntry(
            player_name=name,
            score=score,
            hole_number=hole_number,
            par=par_val,
            round_date=round_date,
            course_name=course_name,
        )
        for name, score, hole_number, par_val, round_date, course_name in worst_entries
    ]

    return TeamLeaderboards(
        lowest_scores_9=_compute_team_leaderboards_for_holes(rounds_9),
        lowest_scores_18=_compute_team_leaderboards_for_holes(rounds_18),
        lowest_9_hole_round_scores=_compute_team_lowest_round_scores(rounds_9, 9),
        lowest_18_hole_round_scores=_compute_team_lowest_round_scores(rounds_18, 18),
        most_9_hole_round_wins=_sorted_count_entries(wins_9, team_names),
        most_18_hole_round_wins=_sorted_count_entries(wins_18, team_names),
        worst_holes=worst_list,
        double_bogey_plus_per_9=_sorted_rate_entries(db9, team_names, ascending=True),
        bogeys_per_9=_sorted_rate_entries(bogey, team_names, ascending=True),
        pars_per_9=_sorted_rate_entries(par, team_names, ascending=False),
        birdies_per_9=_sorted_rate_entries(birdie, team_names, ascending=False),
        eagles_per_9=_sorted_rate_entries(eagle, team_names, ascending=False),
    )


def _compute_hole_difficulty_for_holes(
    rounds: List[Round],
) -> Tuple[List[PlayerStrokeIndexHeatmapEntry], List[StrokeIndexBandEntry]]:
    heatmap_totals: Dict[str, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    band_totals: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))

    for round_ in rounds:
        for round_player in round_.round_players:
            player_name = _player_name(round_player)
            for hole_score in round_player.hole_scores:
                if hole_score.score is None:
                    continue
                par = _hole_par(round_, hole_score.hole_number)
                if par is None:
                    continue

                stroke_index = _hole_stroke_index(round_, hole_score.hole_number)
                score_to_par = hole_score.score - par

                if stroke_index is not None:
                    si_bucket = heatmap_totals[player_name][stroke_index]
                    si_bucket[0] += score_to_par
                    si_bucket[1] += 1

                band_label = _stroke_index_band_label(stroke_index)
                if band_label is not None:
                    band_bucket = band_totals[player_name][band_label]
                    band_bucket[0] += score_to_par
                    band_bucket[1] += 1

    heatmap_entries: List[PlayerStrokeIndexHeatmapEntry] = []
    for player_name in sorted(heatmap_totals):
        for stroke_index in sorted(heatmap_totals[player_name]):
            total_score_to_par, sample_size = heatmap_totals[player_name][stroke_index]
            if sample_size <= 0:
                continue
            heatmap_entries.append(
                PlayerStrokeIndexHeatmapEntry(
                    player_name=player_name,
                    stroke_index=stroke_index,
                    average_score_to_par=round(total_score_to_par / sample_size, 2),
                    rounds_played=int(sample_size),
                )
            )

    band_order = {"1-4": 0, "5-8": 1, "9-12": 2, "13-16": 3}
    band_entries: List[StrokeIndexBandEntry] = []
    for player_name in sorted(band_totals):
        for band_label in sorted(band_totals[player_name], key=lambda label: band_order.get(label, 99)):
            total_score_to_par, sample_size = band_totals[player_name][band_label]
            if sample_size <= 0:
                continue
            band_entries.append(
                StrokeIndexBandEntry(
                    player_name=player_name,
                    band_label=band_label,
                    average_score_to_par=round(total_score_to_par / sample_size, 2),
                    sample_size=int(sample_size),
                )
            )

    return heatmap_entries, band_entries


def _compute_hole_difficulty(rounds: List[Round]) -> HoleDifficultyAnalysis:
    heatmap, bands = _compute_hole_difficulty_for_holes(rounds)
    return HoleDifficultyAnalysis(
        player_score_heatmap=heatmap,
        predicted_score_by_stroke_index=bands,
    )


def _compute_player_ratings(rounds: List[Round]) -> PlayerRatings:
    totals: Dict[str, Dict[str, object]] = defaultdict(
        lambda: {
            "player_name": "",
            "rounds_played": 0,
            "fairways_hit": 0,
            "fairways_possible": 0,
            "gir": 0,
            "gir_possible": 0,
            "drive_distances": [],
            "total_putts": 0,
            "holes_with_putts": 0,
            "scramble_successes": 0,
            "scramble_opportunities": 0,
            "sand_save_successes": 0,
            "sand_save_opportunities": 0,
        }
    )

    for round_ in rounds:
        for round_player in round_.round_players:
            player_name = _player_name(round_player)
            bucket = totals[player_name]
            bucket["player_name"] = player_name
            bucket["rounds_played"] = int(bucket["rounds_played"]) + 1

            if round_player.fairways_hit is not None and round_player.fairways_possible is not None:
                bucket["fairways_hit"] = int(bucket["fairways_hit"]) + round_player.fairways_hit
                bucket["fairways_possible"] = int(bucket["fairways_possible"]) + round_player.fairways_possible

            if round_player.gir is not None and round_player.gir_possible is not None:
                bucket["gir"] = int(bucket["gir"]) + round_player.gir
                bucket["gir_possible"] = int(bucket["gir_possible"]) + round_player.gir_possible

            if round_player.avg_drive_distance is not None:
                bucket["drive_distances"].append(round_player.avg_drive_distance)

            holes_played = len([hs for hs in round_player.hole_scores if hs.score is not None])
            if round_player.total_putts is not None and holes_played > 0:
                bucket["total_putts"] = int(bucket["total_putts"]) + round_player.total_putts
                bucket["holes_with_putts"] = int(bucket["holes_with_putts"]) + holes_played

            if round_player.scramble_successes is not None and round_player.scramble_opportunities is not None:
                bucket["scramble_successes"] = int(bucket["scramble_successes"]) + round_player.scramble_successes
                bucket["scramble_opportunities"] = int(bucket["scramble_opportunities"]) + round_player.scramble_opportunities

            if round_player.sand_save_successes is not None and round_player.sand_save_opportunities is not None:
                bucket["sand_save_successes"] = int(bucket["sand_save_successes"]) + round_player.sand_save_successes
                bucket["sand_save_opportunities"] = int(bucket["sand_save_opportunities"]) + round_player.sand_save_opportunities

    rating_entries: List[PlayerRatingEntry] = []
    for player_name, bucket in totals.items():
        fairway_rate = _ratio(
            int(bucket["fairways_hit"]),
            int(bucket["fairways_possible"]),
        )
        gir_rate = _ratio(
            int(bucket["gir"]),
            int(bucket["gir_possible"]),
        )
        scramble_rate = _ratio(
            int(bucket["scramble_successes"]),
            int(bucket["scramble_opportunities"]),
        )
        sand_save_rate = _ratio(
            int(bucket["sand_save_successes"]),
            int(bucket["sand_save_opportunities"]),
        )
        distance_values = bucket["drive_distances"]
        avg_drive_distance = (
            sum(distance_values) / len(distance_values)
            if distance_values
            else None
        )
        putting_holes = int(bucket["holes_with_putts"])
        putts_per_hole = (
            int(bucket["total_putts"]) / putting_holes
            if putting_holes > 0
            else None
        )

        driving = _weighted_score(
            [
                ((fairway_rate * 100.0) if fairway_rate is not None else None, 0.55),
                (
                    _clamp(((avg_drive_distance - 180.0) / 120.0) * 100.0, 0.0, 100.0)
                    if avg_drive_distance is not None
                    else None,
                    0.45,
                ),
            ]
        )
        fairway = _weighted_score(
            [
                ((gir_rate * 100.0) if gir_rate is not None else None, 1.0),
            ]
        )
        short_game = _weighted_score(
            [
                ((scramble_rate * 100.0) if scramble_rate is not None else None, 0.7),
                ((sand_save_rate * 100.0) if sand_save_rate is not None else None, 0.3),
            ]
        )
        putting = _weighted_score(
            [
                (
                    _clamp(((2.4 - putts_per_hole) / 0.9) * 100.0, 0.0, 100.0)
                    if putts_per_hole is not None
                    else None,
                    1.0,
                ),
            ]
        )

        rating_entries.append(
            PlayerRatingEntry(
                player_name=player_name,
                driving=round(driving, 1),
                fairway=round(fairway, 1),
                short_game=round(short_game, 1),
                putting=round(putting, 1),
                rounds_played=int(bucket["rounds_played"]),
            )
        )

    rating_entries.sort(
        key=lambda entry: (
            -((entry.driving + entry.fairway + entry.short_game + entry.putting) / 4.0),
            entry.player_name.lower(),
        )
    )
    return PlayerRatings(players=rating_entries)


def _merge_v2_results(
    v2_results: List[dict],
) -> Tuple[
    List[PlayerDraft],
    List[Optional[int]],
    List[Optional[int]],
    PredictionMeta,
    Optional[GridMapping],
    Optional[ScorecardGrid],
]:
    """Merge multiple v2 scorecard parse results into a single set of data.

    Each result contains players with hole scores keyed by hole_number (1-18).
    When multiple images cover different holes (e.g. front 9 vs back 9), the
    scores are combined.  Earlier images take priority on conflicts.
    """
    hole_pars: List[Optional[int]] = [None] * 18
    stroke_indexes: List[Optional[int]] = [None] * 18
    predicted_mapping: Optional[GridMapping] = None
    scorecard_grid: Optional[ScorecardGrid] = None
    all_warnings: Dict[str, str] = {}
    min_confidence = 1.0

    # Keyed by normalised name → PlayerDraft (accumulates across images)
    merged_players: Dict[str, PlayerDraft] = {}
    # Preserve insertion order so first-image players come first
    player_order: List[str] = []

    for idx, v2 in enumerate(v2_results):
        v2_players = [PlayerDraft(**p) for p in v2.get("players", [])]

        # Take the first image's grid/mapping for the "adjust mapping" fallback
        if idx == 0:
            predicted_mapping = v2.get("predicted_mapping")
            scorecard_grid = v2.get("scorecard_grid")

        v2_meta = v2.get("prediction_meta") or {}
        min_confidence = min(min_confidence, v2_meta.get("overall_confidence", 1.0))
        for wk, wv in v2_meta.get("field_warnings", {}).items():
            key = f"img{idx+1}_{wk}" if idx > 0 else wk
            all_warnings[key] = wv

        # Merge hole_pars — earlier images win
        img_pars = v2.get("hole_pars") or [None] * 18
        for h in range(18):
            if h < len(img_pars) and img_pars[h] is not None and hole_pars[h] is None:
                hole_pars[h] = img_pars[h]

        img_si = v2.get("stroke_indexes") or [None] * 18
        for h in range(18):
            if h < len(img_si) and img_si[h] is not None and stroke_indexes[h] is None:
                stroke_indexes[h] = img_si[h]

        # Merge players
        for pi, player in enumerate(v2_players):
            key = _normalize_player_name(player.name) if player.name.strip() else f"__pos_{pi}"

            if key not in merged_players:
                # New player: initialise with 18 empty holes
                merged_players[key] = PlayerDraft(
                    name=player.name,
                    team_name=player.team_name,
                    hole_scores=[HoleScoreDraft(hole_number=h + 1) for h in range(18)],
                    stats=PlayerStatsDraft(),
                )
                player_order.append(key)

            target = merged_players[key]

            # Merge hole scores — earlier images win on conflict
            for hs in player.hole_scores:
                if hs.score is not None:
                    existing = next((t for t in target.hole_scores if t.hole_number == hs.hole_number), None)
                    if existing is not None and existing.score is None:
                        existing.score = hs.score

            # Merge stats — earlier images win (fill only where None)
            _merge_stats_into_player(target, player.stats.model_dump())

    meta = PredictionMeta(
        overall_confidence=min_confidence,
        field_warnings=all_warnings,
        has_warnings=bool(all_warnings),
    )
    players = [merged_players[k] for k in player_order]
    return players, hole_pars, stroke_indexes, meta, predicted_mapping, scorecard_grid


def _has_parsed_data(players: List[PlayerDraft]) -> bool:
    """True if we have at least one player with a name and/or any hole score."""
    for p in players:
        if not p.name or p.name.strip() == "":
            continue
        if any(hs.score is not None for hs in p.hole_scores):
            return True
        if p.stats.total_score is not None:
            return True
    return False


def _merge_stats_into_player(
    player: PlayerDraft, stat_dict: Dict[str, Optional[int]],
) -> None:
    """Set stat fields on *player* only where the current value is None."""
    current = player.stats.model_dump()
    changed = False
    for k, v in stat_dict.items():
        if v is not None and current.get(k) is None:
            current[k] = v
            changed = True
    if changed:
        player.stats = PlayerStatsDraft(**current)


def create_app() -> FastAPI:
    app = FastAPI(title="Golf Sim Stats API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173", "http://127.0.0.1:5173",
            "http://localhost:5174", "http://127.0.0.1:5174",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    @app.get("/health")
    def health_check() -> dict:
        return {"status": "ok"}

    @app.post("/api/rounds/ocr-draft", response_model=DraftRound)
    async def create_ocr_draft_round(
        scorecard_images: List[UploadFile] = File(default=[]),
        stats_image: Optional[UploadFile] = File(default=None),
        image_date_hint: Optional[str] = Form(default=None),
    ) -> DraftRound:
        """OCR one or more scorecard images (and optional stats page).

        Multiple scorecard images are merged by hole number so you can
        upload front-9 and back-9 as separate photos.  Earlier images
        take priority when holes overlap.
        """
        if not scorecard_images and not stats_image:
            raise HTTPException(
                status_code=400,
                detail="At least one image must be provided.",
            )

        raw_scorecard_text: Optional[str] = None
        raw_stats_text: Optional[str] = None
        scorecard_grid: Optional[ScorecardGrid] = None
        stats_grid: Optional[ScorecardGrid] = None

        image_date: Optional[date] = None

        # --- Run v2 on each scorecard image ---
        v2_results: List[dict] = []
        for sc_img in scorecard_images:
            sc_bytes = await sc_img.read()
            if image_date is None:
                image_date = get_image_date(sc_bytes)
            sc_text, sc_boxes = extract_word_boxes(sc_bytes)
            if sc_text is None:
                sc_text = ""
            v2 = parse_v2_scorecard(
                image_bytes=sc_bytes,
                word_boxes=sc_boxes,
                raw_text=sc_text,
                image_date=image_date,
                is_warped=True,
                debug=False,
            )
            v2_results.append(v2)
            if raw_scorecard_text is None:
                raw_scorecard_text = sc_text
            else:
                raw_scorecard_text += "\n" + sc_text

        # --- Stats ---
        if stats_image is not None:
            stats_bytes = await stats_image.read()
            if image_date is None:
                image_date = get_image_date(stats_bytes)
            raw_stats_text, stats_word_boxes = extract_word_boxes(stats_bytes)
            if raw_stats_text is None:
                raw_stats_text = ""
        else:
            stats_word_boxes = []

        if image_date is None and image_date_hint:
            try:
                image_date = date.fromisoformat(image_date_hint.strip())
            except ValueError:
                pass

        # --- Merge scorecard v2 results ---
        players: List[PlayerDraft] = []
        predicted_mapping: Optional[GridMapping] = None
        meta = PredictionMeta()
        hole_pars: List[Optional[int]] = [None] * 18
        stroke_indexes: List[Optional[int]] = [None] * 18

        if v2_results:
            players, hole_pars, stroke_indexes, meta, predicted_mapping, scorecard_grid = (
                _merge_v2_results(v2_results)
            )

        # --- Stats grid (v1 path) ---
        if stats_word_boxes:
            stats_grid = word_boxes_to_grid(stats_word_boxes)
        elif raw_stats_text:
            stats_grid = text_to_grid(raw_stats_text)

        if stats_grid and stats_grid.rows:
            player_names = [p.name for p in players] if players else None
            stats_pred = predict_stats(stats_grid, player_names)

            if stats_pred.player_stats:
                if players:
                    for i, sd in enumerate(stats_pred.player_stats):
                        if i < len(players):
                            _merge_stats_into_player(players[i], sd)
                else:
                    for i, sd in enumerate(stats_pred.player_stats):
                        players.append(PlayerDraft(
                            name=f"Player {i + 1}",
                            hole_scores=[
                                HoleScoreDraft(hole_number=h + 1) for h in range(18)
                            ],
                            stats=PlayerStatsDraft(
                                **{k: v for k, v in sd.items() if v is not None}
                            ),
                        ))

                for fname, fc in stats_pred.confidence.items():
                    if fc.value < 0.5:
                        meta.field_warnings[f"stats_{fname}"] = fc.reason
                meta.overall_confidence = min(
                    meta.overall_confidence, stats_pred.overall_confidence,
                )
                meta.has_warnings = bool(meta.field_warnings)

        # --- Fallback: empty template when nothing was extracted ---
        if not _has_parsed_data(players):
            players = [
                PlayerDraft(
                    name=f"Player {i + 1}",
                    hole_scores=[
                        HoleScoreDraft(hole_number=h + 1) for h in range(18)
                    ],
                    stats=PlayerStatsDraft(),
                )
                for i in range(4)
            ]
            meta.overall_confidence = 0.0
            meta.has_warnings = True
            meta.field_warnings["extraction"] = (
                "No data could be extracted from images"
            )

        if len(hole_pars) != 18:
            hole_pars = [None] * 18
        if len(stroke_indexes) != 18:
            stroke_indexes = [None] * 18

        # One grid and mapping per scorecard image (for tabbed "Adjust mapping" UI)
        scorecard_grids = None
        predicted_mappings = None
        if v2_results:
            scorecard_grids = [v.get("scorecard_grid") for v in v2_results]
            predicted_mappings = [v.get("predicted_mapping") for v in v2_results]

        return DraftRound(
            date=image_date,
            players=players,
            hole_pars=hole_pars,
            stroke_indexes=stroke_indexes,
            raw_scorecard_text=raw_scorecard_text,
            raw_stats_text=raw_stats_text,
            scorecard_grid=scorecard_grid,
            stats_grid=stats_grid,
            predicted_mapping=predicted_mapping,
            prediction_meta=meta,
            scorecard_grids=scorecard_grids or None,
            predicted_mappings=predicted_mappings or None,
        )

    @app.post("/api/scorecards/map-grid", response_model=DraftRound)
    def map_grid(payload: MapGridRequest) -> DraftRound:
        """Apply a user-defined grid mapping to produce a DraftRound."""
        try:
            result = apply_grid_mapping(payload.grid, payload.mapping)
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))
        hole_pars = result.get("hole_pars") or [None] * 18
        stroke_indexes = result.get("stroke_indexes") or [None] * 18
        # Avoid passing hole_pars/stroke_indexes twice (they are already in result)
        rest = {k: v for k, v in result.items() if k not in ("hole_pars", "stroke_indexes")}
        return DraftRound(hole_pars=hole_pars, stroke_indexes=stroke_indexes, **rest)

    @app.post("/api/rounds")
    def create_round(payload: DraftRound) -> dict:
        """Persist an edited round: create/find players, round, round_players, hole_scores."""
        session = SessionLocal()
        try:
            hole_pars = payload.hole_pars
            stroke_indexes = payload.stroke_indexes
            if hole_pars and any(p is not None for p in hole_pars):
                hole_pars = (list(hole_pars) + [None] * 18)[:18]
            else:
                hole_pars = None
            if stroke_indexes and any(s is not None for s in stroke_indexes):
                stroke_indexes = (list(stroke_indexes) + [None] * 18)[:18]
            else:
                stroke_indexes = None

            r = Round(
                date=payload.date,
                course_name=payload.course_name or None,
                tee_set=payload.tee_set or None,
                is_team_round=payload.is_team_round,
                hole_pars=hole_pars,
                stroke_indexes=stroke_indexes,
            )
            session.add(r)
            session.flush()

            for p in payload.players:
                existing = session.query(Player).filter(Player.name == p.name).first()
                if existing:
                    player = existing
                else:
                    player = Player(name=p.name)
                    session.add(player)
                    session.flush()

                rp = RoundPlayer(
                    round_id=r.id,
                    player_id=player.id,
                    team_name=p.team_name or None,
                    total_score=p.stats.total_score,
                    out_score=p.stats.out_score,
                    in_score=p.stats.in_score,
                    fairways_hit=p.stats.fairways_hit,
                    fairways_possible=p.stats.fairways_possible,
                    gir=p.stats.gir,
                    gir_possible=p.stats.gir_possible,
                    avg_drive_distance=p.stats.avg_drive_distance,
                    total_putts=p.stats.total_putts,
                    scramble_successes=p.stats.scramble_successes,
                    scramble_opportunities=p.stats.scramble_opportunities,
                    sand_save_successes=p.stats.sand_save_successes,
                    sand_save_opportunities=p.stats.sand_save_opportunities,
                )
                session.add(rp)
                session.flush()

                for hs in p.hole_scores:
                    if hs.score is not None:
                        session.add(
                            HoleScore(
                                round_player_id=rp.id,
                                hole_number=hs.hole_number,
                                score=hs.score,
                            )
                        )

            session.commit()
            return {"id": r.id}
        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            session.close()

    @app.get("/api/rounds", response_model=List[RoundSummary])
    def list_rounds() -> List[RoundSummary]:
        """List all rounds, newest first."""
        session = SessionLocal()
        try:
            rounds = (
                session.query(Round)
                .options(
                    joinedload(Round.round_players).joinedload(RoundPlayer.hole_scores),
                    joinedload(Round.round_players).joinedload(RoundPlayer.player),
                )
                .order_by(Round.created_at.desc())
                .all()
            )
            result = []
            for r in rounds:
                player_names = [rp.player.name for rp in sorted(r.round_players, key=lambda x: x.id) if rp.player]
                result.append(
                    RoundSummary(
                        id=r.id,
                        date=r.date,
                        course_name=r.course_name,
                        tee_set=r.tee_set,
                        is_team_round=r.is_team_round,
                        player_names=player_names,
                        holes_type=_round_holes_type(r),
                    )
                )
            return result
        finally:
            session.close()

    @app.get("/api/rounds/{round_id}", response_model=RoundDetail)
    def get_round(round_id: int) -> RoundDetail:
        """Get a single round by id with players and hole scores."""
        session = SessionLocal()
        try:
            r = session.query(Round).filter(Round.id == round_id).first()
            if r is None:
                raise HTTPException(status_code=404, detail="Round not found")
            players_draft: List[PlayerDraft] = []
            for rp in sorted(r.round_players, key=lambda x: x.id):
                scores_by_hole = {
                    hs.hole_number: hs.score for hs in rp.hole_scores
                }
                hole_scores = [
                    HoleScoreDraft(hole_number=h, score=scores_by_hole.get(h))
                    for h in range(1, 19)
                ]
                stats = PlayerStatsDraft(
                    total_score=rp.total_score,
                    out_score=rp.out_score,
                    in_score=rp.in_score,
                    fairways_hit=rp.fairways_hit,
                    fairways_possible=rp.fairways_possible,
                    gir=rp.gir,
                    gir_possible=rp.gir_possible,
                    avg_drive_distance=rp.avg_drive_distance,
                    total_putts=rp.total_putts,
                    scramble_successes=rp.scramble_successes,
                    scramble_opportunities=rp.scramble_opportunities,
                    sand_save_successes=rp.sand_save_successes,
                    sand_save_opportunities=rp.sand_save_opportunities,
                )
                players_draft.append(
                    PlayerDraft(
                        name=rp.player.name,
                        team_name=rp.team_name,
                        hole_scores=hole_scores,
                        stats=stats,
                    )
                )
            return RoundDetail(
                id=r.id,
                date=r.date,
                course_name=r.course_name,
                tee_set=r.tee_set,
                is_team_round=r.is_team_round,
                players=players_draft,
                hole_pars=getattr(r, "hole_pars", None),
                stroke_indexes=getattr(r, "stroke_indexes", None),
            )
        finally:
            session.close()

    @app.put("/api/rounds/{round_id}")
    def update_round(round_id: int, payload: DraftRound) -> dict:
        """Update an existing round: replace round fields and all round_players/hole_scores."""
        session = SessionLocal()
        try:
            r = session.query(Round).filter(Round.id == round_id).first()
            if r is None:
                raise HTTPException(status_code=404, detail="Round not found")
            hole_pars = payload.hole_pars
            stroke_indexes = payload.stroke_indexes
            if hole_pars and any(p is not None for p in hole_pars):
                hole_pars = (list(hole_pars) + [None] * 18)[:18]
            else:
                hole_pars = None
            if stroke_indexes and any(s is not None for s in stroke_indexes):
                stroke_indexes = (list(stroke_indexes) + [None] * 18)[:18]
            else:
                stroke_indexes = None

            r.date = payload.date
            r.course_name = payload.course_name or None
            r.tee_set = payload.tee_set or None
            r.is_team_round = payload.is_team_round
            r.hole_pars = hole_pars
            r.stroke_indexes = stroke_indexes

            for rp in list(r.round_players):
                for hs in list(rp.hole_scores):
                    session.delete(hs)
                session.delete(rp)

            for p in payload.players:
                existing = session.query(Player).filter(Player.name == p.name).first()
                if existing:
                    player = existing
                else:
                    player = Player(name=p.name)
                    session.add(player)
                    session.flush()

                rp = RoundPlayer(
                    round_id=r.id,
                    player_id=player.id,
                    team_name=p.team_name or None,
                    total_score=p.stats.total_score,
                    out_score=p.stats.out_score,
                    in_score=p.stats.in_score,
                    fairways_hit=p.stats.fairways_hit,
                    fairways_possible=p.stats.fairways_possible,
                    gir=p.stats.gir,
                    gir_possible=p.stats.gir_possible,
                    avg_drive_distance=p.stats.avg_drive_distance,
                    total_putts=p.stats.total_putts,
                    scramble_successes=p.stats.scramble_successes,
                    scramble_opportunities=p.stats.scramble_opportunities,
                    sand_save_successes=p.stats.sand_save_successes,
                    sand_save_opportunities=p.stats.sand_save_opportunities,
                )
                session.add(rp)
                session.flush()

                for hs in p.hole_scores:
                    if hs.score is not None:
                        session.add(
                            HoleScore(
                                round_player_id=rp.id,
                                hole_number=hs.hole_number,
                                score=hs.score,
                            )
                        )

            session.commit()
            return {"id": r.id}
        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            session.close()

    @app.delete("/api/rounds/{round_id}")
    def delete_round(round_id: int) -> dict:
        """Delete a round and its round_players and hole_scores."""
        session = SessionLocal()
        try:
            r = session.query(Round).filter(Round.id == round_id).first()
            if r is None:
                raise HTTPException(status_code=404, detail="Round not found")
            for rp in list(r.round_players):
                for hs in list(rp.hole_scores):
                    session.delete(hs)
                session.delete(rp)
            session.delete(r)
            session.commit()
            return {"id": round_id}
        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            session.close()

    # ---- Scorecard parse v2 endpoint ----

    @app.post("/api/scorecard/parse_v2")
    async def scorecard_parse_v2(
        scorecard_image: UploadFile = File(...),
        image_date_hint: Optional[str] = Form(default=None),
        scorecard_is_warped: Optional[str] = Form(default=None),
        debug: Optional[str] = Form(default=None),
    ) -> dict:
        """Layout-first, constraints-driven scorecard extraction (v2).

        Accepts a single scorecard image, runs OCR, reconstructs the grid
        geometry, infers semantics, validates/repairs, and returns a
        DraftRound-shaped response.

        Set ``debug=true`` to include extra layout diagnostics.
        """
        image_bytes = await scorecard_image.read()

        image_date: Optional[date] = None
        if image_date_hint:
            try:
                image_date = date.fromisoformat(image_date_hint.strip())
            except ValueError:
                pass
        if image_date is None:
            image_date = get_image_date(image_bytes)

        raw_text, word_boxes = extract_word_boxes(image_bytes)

        is_warped = scorecard_is_warped in ("true", "1", "yes")
        want_debug = debug in ("true", "1", "yes")

        result = parse_v2_scorecard(
            image_bytes=image_bytes,
            word_boxes=word_boxes,
            raw_text=raw_text,
            image_date=image_date,
            is_warped=is_warped,
            debug=want_debug,
        )

        # Ensure serialisable grid/mapping types
        grid = result.get("scorecard_grid")
        mapping = result.get("predicted_mapping")
        meta = result.get("prediction_meta")

        return DraftRound(
            date=result.get("date"),
            course_name=result.get("course_name"),
            tee_set=result.get("tee_set"),
            is_team_round=result.get("is_team_round", False),
            players=[PlayerDraft(**p) for p in result.get("players", [])],
            hole_pars=result.get("hole_pars", [None] * 18),
            stroke_indexes=result.get("stroke_indexes", [None] * 18),
            raw_scorecard_text=raw_text,
            scorecard_grid=grid,
            predicted_mapping=mapping,
            prediction_meta=PredictionMeta(**(meta or {})),
        ).model_dump() | (
            {"debug_layout": result["debug_layout"]} if "debug_layout" in result else {}
        ) | (
            {"repaired_cells": result.get("repaired_cells", [])}
        )

    # ---- Analytics endpoints ----

    @app.get("/api/analytics/lowest-round-scores", response_model=List[LowestRoundScoreEntry])
    def analytics_lowest_round_scores() -> List[LowestRoundScoreEntry]:
        """Return each player's best (lowest) round score, with score relative to par where available."""
        session = SessionLocal()
        try:
            return _compute_lowest_round_scores(_load_all_rounds(session))
        finally:
            session.close()

    @app.get("/api/analytics/single-player-leaderboards", response_model=SinglePlayerLeaderboards)
    def analytics_single_player_leaderboards() -> SinglePlayerLeaderboards:
        session = SessionLocal()
        try:
            return _compute_single_player_leaderboards(_load_all_rounds(session))
        finally:
            session.close()

    @app.get("/api/analytics/performance-trends", response_model=PerformanceTrends)
    def analytics_performance_trends() -> PerformanceTrends:
        session = SessionLocal()
        try:
            return _compute_performance_trends(_load_all_rounds(session))
        finally:
            session.close()

    @app.get("/api/analytics/team-leaderboards", response_model=TeamLeaderboards)
    def analytics_team_leaderboards() -> TeamLeaderboards:
        session = SessionLocal()
        try:
            return _compute_team_leaderboards(_load_all_rounds(session))
        finally:
            session.close()

    @app.get("/api/analytics/hole-difficulty", response_model=HoleDifficultyAnalysis)
    def analytics_hole_difficulty() -> HoleDifficultyAnalysis:
        session = SessionLocal()
        try:
            return _compute_hole_difficulty(_load_all_rounds(session))
        finally:
            session.close()

    @app.get("/api/analytics/player-ratings", response_model=PlayerRatings)
    def analytics_player_ratings() -> PlayerRatings:
        session = SessionLocal()
        try:
            return _compute_player_ratings(_load_all_rounds(session))
        finally:
            session.close()

    @app.get("/api/export/share")
    def export_share() -> Response:
        """Export all rounds and analytics as JSON for static share deployment."""
        session = SessionLocal()
        try:
            rounds = _load_all_rounds_with_relations(session)
            rounds_list = sorted(
                rounds,
                key=lambda r: (
                    (r.created_at or datetime.min).timestamp(),
                    r.id,
                ),
                reverse=True,
            )
            rounds_payload = [_round_to_summary(r) for r in rounds_list]
            round_details_payload = {str(r.id): _round_to_detail(r) for r in rounds}

            lowest_9 = _compute_lowest_round_scores(rounds, 9)
            lowest_18 = _compute_lowest_round_scores(rounds, 18)
            lowest_round_scores = lowest_9 + lowest_18

            payload = {
                "rounds": [r.model_dump(mode="json") for r in rounds_payload],
                "roundDetails": {
                    k: v.model_dump(mode="json") for k, v in round_details_payload.items()
                },
                "lowestRoundScores": [e.model_dump(mode="json") for e in lowest_round_scores],
                "singlePlayerLeaderboards": _compute_single_player_leaderboards(rounds).model_dump(
                    mode="json"
                ),
                "performanceTrends": _compute_performance_trends(rounds).model_dump(mode="json"),
                "teamLeaderboards": _compute_team_leaderboards(rounds).model_dump(mode="json"),
                "holeDifficulty": _compute_hole_difficulty(rounds).model_dump(mode="json"),
                "playerRatings": _compute_player_ratings(rounds).model_dump(mode="json"),
            }
            return Response(
                content=json.dumps(payload, default=str),
                media_type="application/json",
            )
        finally:
            session.close()

    # ---- Temporary test endpoints for perspective correction ----

    @app.post("/api/test/detect-corners")
    async def detect_corners(
        image: UploadFile = File(...),
    ) -> dict:
        """Auto-detect the 4 corners of the scorecard region in the image."""
        image_bytes = await image.read()
        corners = auto_detect_corners(image_bytes)
        if corners is None:
            raise HTTPException(
                status_code=422,
                detail="Could not auto-detect corners in image",
            )
        return {"corners": [{"x": x, "y": y} for x, y in corners]}

    @app.post("/api/test/warp-image")
    async def warp_image(
        image: UploadFile = File(...),
        corners: str = Form(...),
    ) -> Response:
        """Apply perspective correction given 4 corner points.

        *corners* is a JSON string: [{"x": ..., "y": ...}, ...] (4 points).
        Returns the corrected image as JPEG bytes.
        """
        import json

        image_bytes = await image.read()
        try:
            pts = json.loads(corners)
            if len(pts) != 4:
                raise ValueError("Exactly 4 corner points required")
            point_tuples = [(float(p["x"]), float(p["y"])) for p in pts]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=f"Invalid corners: {exc}")

        try:
            result_bytes = perspective_warp(image_bytes, point_tuples)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return Response(content=result_bytes, media_type="image/jpeg")

    return app


app = create_app()
