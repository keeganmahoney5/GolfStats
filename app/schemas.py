from __future__ import annotations

from datetime import date
from typing import Optional, List

from pydantic import BaseModel, Field


class DraftRoundMeta(BaseModel):
    """Basic metadata about a golf round inferred from OCR or provided by the client."""

    date: Optional[date] = None
    course_name: Optional[str] = None
    tee_set: Optional[str] = None
    is_team_round: bool = False


class DraftHoleScore(BaseModel):
    """Hole-by-hole score for a given player."""

    player_name: str
    hole_number: int
    score: Optional[int] = None


class DraftPlayerStats(BaseModel):
    """Per-player aggregated stats for a round."""

    name: str
    team_name: Optional[str] = None

    total_score: Optional[int] = None

    fairways_hit: Optional[int] = None
    fairways_possible: Optional[int] = None

    gir: Optional[int] = None
    gir_possible: Optional[int] = None

    avg_drive_distance: Optional[float] = None
    total_putts: Optional[int] = None

    scramble_successes: Optional[int] = None
    scramble_opportunities: Optional[int] = None

    sand_save_successes: Optional[int] = None
    sand_save_opportunities: Optional[int] = None


class DraftRound(BaseModel):
    """
    High-level structure returned by OCR + parsing.

    This is meant to be edited/confirmed on the front-end before being
    converted into persisted ORM models.
    """

    meta: DraftRoundMeta = Field(default_factory=DraftRoundMeta)
    players: List[DraftPlayerStats] = Field(default_factory=list)
    hole_scores: List[DraftHoleScore] = Field(default_factory=list)

