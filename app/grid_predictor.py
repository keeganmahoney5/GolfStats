"""
Deterministic heuristic engine that predicts row/column labels for scorecard
and stats grids.  Every prediction carries a per-field confidence score so
the caller can partial-fill (leave uncertain fields blank).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .grid import (
    ScorecardGrid,
    GridMapping,
    clean_grid,
    suggest_par_and_si_rows,
    _try_int,
    _safe_get,
)

_INT_RE = re.compile(r"^-?\d+$")
_PCT_RE = re.compile(r"^(\d+)\s*%$")
_RATIO_RE = re.compile(r"^(\d+)\s*/\s*(\d+)$")
_YD_RE = re.compile(r"^(\d+)\s*(?:YD|yd|Yd)$")
_RANK_RE = re.compile(r"^[1-8]$")

_HOLE_NUMBERS_18 = frozenset(str(i) for i in range(1, 19))
_HEADER_KEYWORDS = frozenset({"hole", "holes", "#", "no", "no."})
_SUBTOTAL_KEYWORDS = frozenset({"out", "in", "f9", "b9", "front", "back"})
_TOTAL_KEYWORDS = frozenset({"total", "gross", "net", "score"})


def _normalize_header_cell(cell: str) -> str:
    """Normalize header cell for keyword matching: strip, lower, remove all whitespace.
    So 'OUT', '  OUT  ', 'O U T' all become 'out'. Handles all-caps and OCR spacing."""
    return re.sub(r"\s+", "", (cell or "").strip().lower())

_SKIP_ROW_KEYWORDS = frozenset({
    "par", "si", "hcp", "handicap", "stroke", "index",
    "print", "continue", "scorecard", "leaderboard",
    "stats", "round", "dell", "wins", ">", "b9", "f9",
    "single", "team", "hole", "holes",
})

_STAT_NAME_MAP: Dict[str, str] = {
    "fairway": "fairways", "fairways": "fairways", "fwy": "fairways",
    "gir": "gir", "green": "gir", "greens": "gir",
    "putt": "putts", "putts": "putts",
    "drive": "drive_distance", "driving": "drive_distance",
    "distance": "drive_distance",
    "scramble": "scramble", "scrambling": "scramble",
    "sand": "sand_save", "bunker": "sand_save",
    "total": "total_score", "score": "total_score",
}


# ---------------------------------------------------------------------------
# Result data-classes
# ---------------------------------------------------------------------------

@dataclass
class FieldConfidence:
    value: float
    reason: str = ""


@dataclass
class PredictionResult:
    mapping: GridMapping
    confidence: Dict[str, FieldConfidence] = field(default_factory=dict)
    overall_confidence: float = 0.0

    @property
    def has_low_confidence_fields(self) -> bool:
        return any(fc.value < 0.5 for fc in self.confidence.values())


@dataclass
class StatsPrediction:
    player_stats: List[Dict[str, Optional[int]]]
    confidence: Dict[str, FieldConfidence] = field(default_factory=dict)
    overall_confidence: float = 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict_scorecard_mapping(grid: ScorecardGrid) -> PredictionResult:
    """Analyse a scorecard grid and predict the GridMapping fields."""
    grid = clean_grid(grid)
    if not grid.rows:
        return _empty_prediction("Empty grid")

    header_idx, header_conf = _detect_header_row(grid)

    if header_idx is not None:
        hole_cols, holes_conf = _detect_hole_cols_from_header(grid.rows[header_idx])
        total_col, total_conf = _detect_total_col(grid.rows[header_idx], hole_cols)
    else:
        hole_cols, holes_conf = _detect_hole_cols_from_data(grid)
        total_col, total_conf = None, FieldConfidence(0.2, "No header row found")

    first_data = (header_idx + 1) if header_idx is not None else 0
    name_col, name_conf = _detect_name_col(
        grid, header_idx, set(hole_cols), total_col, first_data,
    )

    first_player, last_player, player_conf = _detect_player_rows(
        grid, header_idx, name_col, hole_cols,
    )

    first_hole_number = _infer_first_hole_number(
        grid, header_idx, hole_cols,
    )

    mapping = GridMapping(
        header_row=header_idx,
        name_col=name_col,
        hole_cols=hole_cols,
        total_col=total_col,
        first_player_row=first_player,
        last_player_row=last_player,
        first_hole_number=first_hole_number,
    )

    par_row, si_row = suggest_par_and_si_rows(grid, mapping)
    if par_row is not None or si_row is not None:
        mapping = mapping.model_copy(update={"par_row": par_row, "stroke_index_row": si_row})

    if header_idx is not None and hole_cols:
        out_col, in_col, out_conf, in_conf = _detect_out_in_cols(grid.rows[header_idx], set(hole_cols))
        if out_col is not None or in_col is not None:
            mapping = mapping.model_copy(update={"out_col": out_col, "in_col": in_col})
        confidence_out_in = {"out_col": out_conf, "in_col": in_conf}
    else:
        confidence_out_in = {"out_col": FieldConfidence(0.5, "No header for Out/In"), "in_col": FieldConfidence(0.5, "No header for Out/In")}

    confidence = {
        "header_row": header_conf,
        "hole_cols": holes_conf,
        "total_col": total_conf,
        "name_col": name_conf,
        "player_rows": player_conf,
        **confidence_out_in,
    }
    overall = min(fc.value for fc in confidence.values())

    return PredictionResult(
        mapping=mapping,
        confidence=confidence,
        overall_confidence=overall,
    )


def predict_stats(
    grid: ScorecardGrid,
    player_names: list[str] | None = None,
) -> StatsPrediction:
    """Extract per-player stats from a stats grid."""
    grid = clean_grid(grid)
    if not grid.rows:
        return StatsPrediction(player_stats=[], overall_confidence=0.0)

    result = _try_keyword_columns(grid, player_names)
    if result is not None:
        return result

    result = _try_keyword_rows(grid, player_names)
    if result is not None:
        return result

    return _try_simulator_stats(grid, player_names)


# ---------------------------------------------------------------------------
# Scorecard detection helpers
# ---------------------------------------------------------------------------

def _empty_prediction(reason: str) -> PredictionResult:
    return PredictionResult(
        mapping=GridMapping(),
        overall_confidence=0.0,
        confidence={"overall": FieldConfidence(0.0, reason)},
    )


def _detect_header_row(
    grid: ScorecardGrid,
) -> Tuple[Optional[int], FieldConfidence]:
    best_idx: Optional[int] = None
    best_score = 0.0
    for ri, row in enumerate(grid.rows):
        score = _score_header_candidate(row, ri, len(grid.rows))
        if score > best_score:
            best_score = score
            best_idx = ri

    if best_score >= 5.0:
        return best_idx, FieldConfidence(1.0, "Strong header detected")
    if best_score >= 3.0:
        return best_idx, FieldConfidence(0.7, "Likely header row")
    if best_score >= 1.5:
        return best_idx, FieldConfidence(0.4, "Weak header signal")
    return None, FieldConfidence(0.1, "No header row found")


def _score_header_candidate(
    row: List[str], row_idx: int, total_rows: int,
) -> float:
    score = 0.0
    cells_lower = [c.strip().lower() for c in row]

    if any(c in _HEADER_KEYWORDS for c in cells_lower):
        score += 3.0
    if any(c in _SUBTOTAL_KEYWORDS for c in cells_lower):
        score += 1.0
    if any(c in _TOTAL_KEYWORDS for c in cells_lower):
        score += 1.0

    hole_nums = sorted(int(c.strip()) for c in row if c.strip() in _HOLE_NUMBERS_18)
    score += len(hole_nums) * 0.5

    if len(hole_nums) >= 3:
        score += _longest_consecutive_run(hole_nums) * 0.8

    frac = row_idx / max(total_rows, 1)
    if frac > 0.5:
        score *= 0.3
    elif frac > 0.3:
        score *= 0.7

    return score


def _longest_consecutive_run(sorted_ints: List[int]) -> int:
    if not sorted_ints:
        return 0
    run = 1
    best = 1
    for a, b in zip(sorted_ints, sorted_ints[1:]):
        if b == a + 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def _detect_hole_cols_from_header(
    header: List[str],
) -> Tuple[List[int], FieldConfidence]:
    skip = _SUBTOTAL_KEYWORDS | _TOTAL_KEYWORDS
    candidates: List[Tuple[int, int]] = []
    for ci, cell in enumerate(header):
        s = cell.strip()
        if s.lower() in skip:
            continue
        if s in _HOLE_NUMBERS_18:
            candidates.append((ci, int(s)))

    if not candidates:
        return [], FieldConfidence(0.0, "No hole numbers in header")

    candidates.sort(key=lambda x: x[1])
    cols = [ci for ci, _ in candidates]
    nums = [n for _, n in candidates]

    expected = list(range(nums[0], nums[0] + len(nums)))
    if nums == expected:
        conf = 1.0 if len(cols) >= 9 else 0.7
        return cols, FieldConfidence(conf, f"Sequential holes {nums[0]}-{nums[-1]}")

    gaps = sum(1 for a, b in zip(nums, nums[1:]) if b != a + 1)
    conf = max(0.3, 0.8 - gaps * 0.1)
    return cols, FieldConfidence(conf, f"{len(cols)} hole cols with {gaps} gap(s)")


def _detect_hole_cols_from_data(
    grid: ScorecardGrid,
) -> Tuple[List[int], FieldConfidence]:
    """When no header exists, find the longest run of consistently numeric columns."""
    if not grid.rows:
        return [], FieldConfidence(0.0, "No data rows")

    num_cols = max(len(r) for r in grid.rows)
    col_numeric_ratio: List[float] = []

    for ci in range(num_cols):
        numeric = 0
        total = 0
        for row in grid.rows:
            cell = _safe_get(row, ci, "").strip()
            if not cell:
                continue
            total += 1
            if _INT_RE.match(cell):
                numeric += 1
        col_numeric_ratio.append(numeric / max(total, 1))

    best_start = 0
    best_len = 0
    cur_start = -1
    cur_len = 0
    for ci, ratio in enumerate(col_numeric_ratio):
        if ratio > 0.6:
            if cur_start < 0:
                cur_start = ci
                cur_len = 1
            else:
                cur_len += 1
            if cur_len > best_len:
                best_start = cur_start
                best_len = cur_len
        else:
            cur_start = -1
            cur_len = 0

    if best_len >= 3:
        cols = list(range(best_start, best_start + min(best_len, 18)))
        conf = min(1.0, best_len / 9 * 0.6)
        return cols, FieldConfidence(conf, f"Inferred {len(cols)} numeric columns")

    return [], FieldConfidence(0.1, "Could not determine hole columns from data")


def _cell_looks_total(n: str) -> bool:
    """True if normalized cell is total/gross/net (exact or prefix e.g. 'totalscore')."""
    if not n:
        return False
    if n in _TOTAL_KEYWORDS:
        return True
    return any(n.startswith(kw) for kw in _TOTAL_KEYWORDS)


def _cell_looks_out(n: str) -> bool:
    """True if normalized cell is out/front 9 (exact or prefix)."""
    if not n:
        return False
    if n in _OUT_HEADER_KEYWORDS or (n.startswith("front") and "9" in n):
        return True
    return n.startswith("out")


def _cell_looks_in(n: str) -> bool:
    """True if normalized cell is in/back 9. Avoid matching 'index', 'inside' by requiring short or exact."""
    if not n:
        return False
    if n in _IN_HEADER_KEYWORDS or (n.startswith("back") and "9" in n):
        return True
    return n == "in" or (n.startswith("in") and len(n) <= 4)


def _detect_total_col(
    header: List[str], hole_cols: List[int],
) -> Tuple[Optional[int], FieldConfidence]:
    hole_set = set(hole_cols)
    for ci, cell in enumerate(header):
        n = _normalize_header_cell(cell)
        if _cell_looks_total(n) and ci not in hole_set:
            return ci, FieldConfidence(1.0, f"Keyword '{cell.strip()}' at col {ci}")

    if hole_cols:
        last = max(hole_cols)
        for ci in range(last + 1, len(header)):
            n = _normalize_header_cell(header[ci])
            if _cell_looks_out(n) or _cell_looks_in(n) or n in _SUBTOTAL_KEYWORDS:
                continue
            if n and ci not in hole_set:
                return ci, FieldConfidence(0.5, f"First col after holes (col {ci})")

    return None, FieldConfidence(0.3, "No total column found")


# Normalized forms only (after _normalize_header_cell: no spaces, lower). "front 9" -> "front9".
_OUT_HEADER_KEYWORDS = frozenset({"out", "f9", "front", "front9"})
_IN_HEADER_KEYWORDS = frozenset({"in", "b9", "back", "back9"})


def _detect_out_in_cols(
    header: List[str], hole_set: set
) -> Tuple[Optional[int], Optional[int], FieldConfidence, FieldConfidence]:
    """Find columns labeled OUT (front 9 total) and IN (back 9 total) in header.
    Uses normalized matching so 'OUT', 'O U T', 'Out' all match. Returns (out_col, in_col, out_conf, in_conf)."""
    out_col, in_col = None, None
    for ci, cell in enumerate(header):
        n = _normalize_header_cell(cell)
        if ci in hole_set:
            continue
        if _cell_looks_out(n):
            out_col = ci
        elif _cell_looks_in(n):
            in_col = ci
    out_conf = FieldConfidence(1.0, f"Out at col {out_col}") if out_col is not None else FieldConfidence(0.5, "No Out column (optional)")
    in_conf = FieldConfidence(1.0, f"In at col {in_col}") if in_col is not None else FieldConfidence(0.5, "No In column (optional)")
    return (out_col, in_col, out_conf, in_conf)


def _detect_name_col(
    grid: ScorecardGrid,
    header_idx: Optional[int],
    hole_col_set: set,
    total_col: Optional[int],
    first_data_row: int,
) -> Tuple[int, FieldConfidence]:
    num_cols = max(len(r) for r in grid.rows) if grid.rows else 0
    skip = hole_col_set | ({total_col} if total_col is not None else set())

    best_col = 0
    best_score = -1.0

    for ci in range(num_cols):
        if ci in skip:
            continue
        text_count = 0
        total = 0
        for ri in range(first_data_row, len(grid.rows)):
            if ri == header_idx:
                continue
            cell = _safe_get(grid.rows[ri], ci, "").strip()
            if not cell:
                continue
            total += 1
            if any(ch.isalpha() for ch in cell) and not _INT_RE.match(cell):
                text_count += 1
        if total == 0:
            continue
        sc = text_count / total - ci * 0.02
        if sc > best_score:
            best_score = sc
            best_col = ci

    if best_score > 0.5:
        return best_col, FieldConfidence(min(1.0, best_score + 0.2), f"Col {best_col}: mostly text")
    if best_score > 0:
        return best_col, FieldConfidence(0.4, f"Col {best_col}: some text")
    return 0, FieldConfidence(0.2, "Defaulting to col 0")


def _detect_player_rows(
    grid: ScorecardGrid,
    header_idx: Optional[int],
    name_col: int,
    hole_cols: List[int],
) -> Tuple[int, Optional[int], FieldConfidence]:
    start = (header_idx + 1) if header_idx is not None else 0
    player_rows: List[int] = []

    for ri in range(start, len(grid.rows)):
        row = grid.rows[ri]
        first_cell = _safe_get(row, 0, "").strip().lower()
        name_cell = _safe_get(row, name_col, "").strip()

        if first_cell in _SKIP_ROW_KEYWORDS or name_cell.lower() in _SKIP_ROW_KEYWORDS:
            continue
        if not name_cell or not any(ch.isalpha() for ch in name_cell):
            continue

        has_score = any(
            _try_int(_safe_get(row, ci, "")) is not None for ci in hole_cols
        ) if hole_cols else True

        if has_score:
            player_rows.append(ri)

    if not player_rows:
        return start, None, FieldConfidence(0.1, "No player rows detected")

    conf = min(1.0, len(player_rows) * 0.25 + 0.3)
    return (
        player_rows[0],
        player_rows[-1],
        FieldConfidence(conf, f"{len(player_rows)} player(s) found"),
    )


def _infer_first_hole_number(
    grid: ScorecardGrid,
    header_idx: Optional[int],
    hole_cols: List[int],
) -> int:
    """If the header labels are 10-18 (back nine), return 10; otherwise 1."""
    if header_idx is None or not hole_cols:
        return 1
    header = grid.rows[header_idx]
    first_label = _safe_get(header, hole_cols[0], "").strip()
    try:
        first_num = int(first_label)
        if 10 <= first_num <= 18:
            return first_num
    except ValueError:
        pass
    return 1


# ---------------------------------------------------------------------------
# Stats prediction helpers
# ---------------------------------------------------------------------------

def _parse_stat_cell(cell: str) -> Tuple[str, Optional[int], Optional[int]]:
    """Parse a stats cell. Returns (type, value1, value2)."""
    s = cell.strip()
    if not s or s in ("-", "\u2013", "\u2014", "N/A", "n/a"):
        return ("none", None, None)
    m = _PCT_RE.match(s)
    if m:
        return ("pct", int(m.group(1)), 100)
    m = _RATIO_RE.match(s)
    if m:
        return ("ratio", int(m.group(1)), int(m.group(2)))
    m = _YD_RE.match(s)
    if m:
        return ("yd", int(m.group(1)), None)
    if _INT_RE.match(s):
        return ("int", int(s), None)
    return ("unknown", None, None)


def _match_stat_keyword(text: str) -> Optional[str]:
    lower = text.strip().lower()
    for keyword, name in _STAT_NAME_MAP.items():
        if keyword in lower:
            return name
    return None


def _empty_player_stats() -> Dict[str, Optional[int]]:
    return {
        "total_score": None,
        "fairways_hit": None, "fairways_possible": None,
        "gir": None, "gir_possible": None,
        "avg_drive_distance": None, "total_putts": None,
        "scramble_successes": None, "scramble_opportunities": None,
        "sand_save_successes": None, "sand_save_opportunities": None,
    }


def _apply_stat_value(
    stats: Dict[str, Optional[int]], stat_name: str, cell: str,
) -> None:
    vtype, v1, v2 = _parse_stat_cell(cell)
    if vtype == "none" or v1 is None:
        return
    if stat_name == "fairways":
        stats["fairways_hit"] = v1
        if v2 is not None:
            stats["fairways_possible"] = v2
    elif stat_name == "gir":
        stats["gir"] = v1
        if v2 is not None:
            stats["gir_possible"] = v2
    elif stat_name == "putts":
        stats["total_putts"] = v1
    elif stat_name == "drive_distance":
        stats["avg_drive_distance"] = v1
    elif stat_name == "scramble":
        stats["scramble_successes"] = v1
        if v2 is not None:
            stats["scramble_opportunities"] = v2
    elif stat_name == "sand_save":
        stats["sand_save_successes"] = v1
        if v2 is not None:
            stats["sand_save_opportunities"] = v2
    elif stat_name == "total_score":
        stats["total_score"] = v1


def _try_keyword_columns(
    grid: ScorecardGrid, player_names: list[str] | None,
) -> Optional[StatsPrediction]:
    """Header row with stats keywords as column names."""
    if len(grid.rows) < 2:
        return None

    for header_ri in range(min(3, len(grid.rows))):
        row = grid.rows[header_ri]
        col_map: Dict[int, str] = {}
        for ci, cell in enumerate(row):
            stat = _match_stat_keyword(cell)
            if stat:
                col_map[ci] = stat
        if len(col_map) < 2:
            continue

        name_ci = -1
        for ci, cell in enumerate(row):
            lower = cell.strip().lower()
            if lower in ("name", "player", "#", "rank"):
                name_ci = ci
                break
        if name_ci < 0:
            for ci in range(len(row)):
                if ci not in col_map:
                    name_ci = ci
                    break

        results: List[Dict[str, Optional[int]]] = []
        for ri in range(header_ri + 1, len(grid.rows)):
            data_row = grid.rows[ri]
            name_cell = _safe_get(data_row, name_ci, "").strip()
            if not name_cell or name_cell.lower() in _SKIP_ROW_KEYWORDS:
                continue
            stats = _empty_player_stats()
            for ci, stat_name in col_map.items():
                _apply_stat_value(stats, stat_name, _safe_get(data_row, ci, ""))
            results.append(stats)

        if results:
            conf = min(1.0, len(col_map) / 4)
            return StatsPrediction(
                player_stats=results,
                overall_confidence=conf,
                confidence={"method": FieldConfidence(conf, "Keyword columns")},
            )

    return None


def _try_keyword_rows(
    grid: ScorecardGrid, player_names: list[str] | None,
) -> Optional[StatsPrediction]:
    """Transposed layout: stat names in first column, players in other columns."""
    if len(grid.rows) < 2 or not grid.rows[0]:
        return None

    row_map: Dict[int, str] = {}
    for ri, row in enumerate(grid.rows):
        first = _safe_get(row, 0, "")
        stat = _match_stat_keyword(first)
        if stat:
            row_map[ri] = stat

    if len(row_map) < 2:
        return None

    num_player_cols = max(len(r) for r in grid.rows) - 1
    if num_player_cols < 1:
        return None

    results: List[Dict[str, Optional[int]]] = []
    for pi in range(1, num_player_cols + 1):
        stats = _empty_player_stats()
        for ri, stat_name in row_map.items():
            _apply_stat_value(stats, stat_name, _safe_get(grid.rows[ri], pi, ""))
        results.append(stats)

    conf = min(1.0, len(row_map) / 4)
    return StatsPrediction(
        player_stats=results,
        overall_confidence=conf,
        confidence={"method": FieldConfidence(conf, "Keyword rows (transposed)")},
    )


def _try_simulator_stats(
    grid: ScorecardGrid, player_names: list[str] | None,
) -> StatsPrediction:
    """
    Fallback for simulator stats: rank markers followed by positional values
    (percentages, YD suffix, plain integers).
    """
    results: List[Dict[str, Optional[int]]] = []
    overall_conf = 0.3
    ri = 0
    while ri < len(grid.rows):
        row = grid.rows[ri]
        tokens_flat = [c.strip() for c in row if c.strip()]

        is_marker = len(tokens_flat) >= 1 and _RANK_RE.match(tokens_flat[0])

        if is_marker:
            value_tokens: List[str] = []
            for t in tokens_flat[1:]:
                if _RANK_RE.match(t):
                    break
                if (
                    any(ch.isalpha() for ch in t)
                    and not _PCT_RE.match(t)
                    and not _YD_RE.match(t)
                ):
                    continue
                value_tokens.append(t)

            ri += 1
            while ri < len(grid.rows):
                next_row = grid.rows[ri]
                next_tokens = [c.strip() for c in next_row if c.strip()]
                if not next_tokens:
                    ri += 1
                    continue
                if _RANK_RE.match(next_tokens[0]):
                    break
                for t in next_tokens:
                    value_tokens.append(t)
                ri += 1

            stats = _empty_player_stats()
            pct_idx = 0
            int_vals: List[int] = []
            for t in value_tokens:
                vtype, v1, v2 = _parse_stat_cell(t)
                if vtype == "pct" and v1 is not None:
                    _assign_pct(stats, pct_idx, v1)
                    pct_idx += 1
                elif vtype == "ratio" and v1 is not None:
                    _assign_ratio(stats, pct_idx, v1, v2)
                    pct_idx += 1
                elif vtype == "yd" and v1 is not None:
                    stats["avg_drive_distance"] = v1
                elif vtype == "int" and v1 is not None:
                    int_vals.append(v1)
                elif vtype == "none":
                    pct_idx += 1

            if int_vals and stats["total_putts"] is None:
                stats["total_putts"] = int_vals[0]
            if len(int_vals) >= 2 and stats["total_score"] is None:
                stats["total_score"] = int_vals[-1]

            results.append(stats)
            overall_conf = 0.5
        else:
            ri += 1

    if not results:
        return StatsPrediction(player_stats=[], overall_confidence=0.0)

    return StatsPrediction(
        player_stats=results,
        overall_confidence=overall_conf,
        confidence={"method": FieldConfidence(overall_conf, "Simulator format (positional)")},
    )


def _assign_pct(stats: Dict[str, Optional[int]], idx: int, value: int) -> None:
    if idx == 0:
        stats["fairways_hit"] = value
        stats["fairways_possible"] = 100
    elif idx == 1:
        stats["gir"] = value
        stats["gir_possible"] = 100
    elif idx == 2:
        stats["scramble_successes"] = value
        stats["scramble_opportunities"] = 100
    elif idx == 3:
        stats["sand_save_successes"] = value
        stats["sand_save_opportunities"] = 100


def _assign_ratio(
    stats: Dict[str, Optional[int]], idx: int, num: int, den: Optional[int],
) -> None:
    if idx == 0:
        stats["fairways_hit"] = num
        stats["fairways_possible"] = den
    elif idx == 1:
        stats["gir"] = num
        stats["gir_possible"] = den
    elif idx == 2:
        stats["scramble_successes"] = num
        stats["scramble_opportunities"] = den
    elif idx == 3:
        stats["sand_save_successes"] = num
        stats["sand_save_opportunities"] = den
