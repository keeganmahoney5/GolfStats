"""Pydantic / dataclass models for scorecard parse v2.

All v2-internal types live here. The public output is converted to the
existing ``DraftRound`` shape from ``app.main`` so the frontend contract
stays unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enriched OCR token (superset of the v1 WordBox)
# ---------------------------------------------------------------------------

@dataclass
class OcrToken:
    """Single word from Vision OCR with full geometry and confidence."""
    text: str
    mid_x: float
    mid_y: float
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    confidence: float = 1.0

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> Tuple[float, float]:
        return (self.mid_x, self.mid_y)


# ---------------------------------------------------------------------------
# Grid geometry
# ---------------------------------------------------------------------------

@dataclass
class CellRect:
    """Pixel-space rectangle for one grid cell."""
    row: int
    col: int
    x_min: float
    x_max: float
    y_min: float
    y_max: float


@dataclass
class CellCandidate:
    """A single OCR reading that falls inside a cell."""
    text: str
    confidence: float
    distance_to_center: float
    is_numeric: bool
    box_height: float


@dataclass
class CellValue:
    """Resolved value for one grid cell with ranked candidates."""
    row: int
    col: int
    best_text: str
    confidence: float
    candidates: List[CellCandidate] = field(default_factory=list)


@dataclass
class GridGeometry:
    """Detected table structure: row/column boundaries and cells."""
    col_boundaries: List[float]
    row_boundaries: List[float]
    cells: List[CellRect] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    strategy: str = "unknown"
    strategy_confidence: float = 0.0

    @property
    def n_rows(self) -> int:
        return max(len(self.row_boundaries) - 1, 0)

    @property
    def n_cols(self) -> int:
        return max(len(self.col_boundaries) - 1, 0)


# ---------------------------------------------------------------------------
# Repair / validation
# ---------------------------------------------------------------------------

@dataclass
class CellRepair:
    """Record of one automatic correction."""
    row: int
    col: int
    old_value: str
    new_value: str
    reason: str


@dataclass
class ValidationResult:
    """Outcome of the constraint-validation + repair pass."""
    is_consistent: bool
    repairs: List[CellRepair] = field(default_factory=list)
    needs_review: bool = False
    warnings: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Debug payload (optional, returned when debug=true)
# ---------------------------------------------------------------------------

class DebugLayout(BaseModel):
    """Serialisable debug data for v2 parse."""
    strategy_used: str = "unknown"
    strategy_confidence: float = 0.0
    col_boundaries: List[float] = []
    row_boundaries: List[float] = []
    n_tokens: int = 0
    n_rows: int = 0
    n_cols: int = 0
    panel_detected: bool = False
    repaired_cells: List[dict] = []
    cell_confidences: List[dict] = []


# ---------------------------------------------------------------------------
# Full v2 result (internal, before adapter to DraftRound)
# ---------------------------------------------------------------------------

@dataclass
class ParseV2Result:
    """Complete output of the v2 parser, before conversion to DraftRound."""
    grid_text: List[List[str]] = field(default_factory=list)
    cell_values: List[List[CellValue]] = field(default_factory=lambda: [])
    geometry: Optional[GridGeometry] = None
    validation: Optional[ValidationResult] = None
    overall_confidence: float = 0.0

    # Semantic labels (row indices, col indices)
    hole_row: Optional[int] = None
    par_row: Optional[int] = None
    si_row: Optional[int] = None
    player_rows: List[int] = field(default_factory=list)
    hole_cols: List[int] = field(default_factory=list)
    out_col: Optional[int] = None
    in_col: Optional[int] = None
    total_col: Optional[int] = None
    name_col: Optional[int] = None
    first_hole_number: int = 1
