from __future__ import annotations

import re
from typing import List

from .schemas import DraftHoleScore, DraftPlayerStats, DraftRound, DraftRoundMeta


_INT_RE = re.compile(r"^-?\d+$")
_RATIO_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
_SINGLE_DIGIT_RE = re.compile(r"^\d$")
_SINGLE_LETTER_RE = re.compile(r"^[A-Za-z]$")
# Simulator: rank 1-4 only (avoids par row digits like 3, 4, 5)
_RANK_RE = re.compile(r"^[1-4]$")
_RANK_LETTER_RE = re.compile(r"^([1-4])([A-Za-z])$")
# Stats screen: percentages and drive distance
_PCT_RE = re.compile(r"^(\d+)%$", re.IGNORECASE)
_YD_RE = re.compile(r"^(\d+)YD$", re.IGNORECASE)

_SIMULATOR_STATS_FOOTER = frozenset({"print", "continue", "dell", "round", "stats", "→", ">", "li"})

# Simulator UI / header words to skip when they appear as a full line or line start
_SCORECARD_SKIP_WORDS = frozenset({
    "hole", "out", "in", "total", "gross", "net", "b9", "f9", "front", "back",
    "print", "continue", "round", "stats", "leaderboard", "scorecard", "single",
    "dell", "wins", ">",
})


def _non_empty_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_header_line(line: str, tokens: List[str]) -> bool:
    """Skip lines that are clearly headers or UI, not player rows."""
    lower = line.lower()
    if "hole" in lower or ("out" in lower and "in" in lower):
        return True
    # Line that is only skip words / numbers (e.g. "OUT TOTAL", "B9 NET GROSS")
    if all(t.lower() in _SCORECARD_SKIP_WORDS or _INT_RE.match(t) for t in tokens):
        return True
    # Single word or two-word header. Treat a lone number as a header, but allow
    # "rank + name" lines like "1 Kevin" or "1 Team One" to pass through.
    if len(tokens) <= 2 and (
        tokens[0].lower() in _SCORECARD_SKIP_WORDS
        or (len(tokens) == 1 and _INT_RE.match(tokens[0]))
    ):
        return True
    return False


def _parse_simulator_player_line(
    tokens: List[str],
) -> tuple[str, List[int]] | None:
    """
    Parse a line like "1 K 4 5 7 4 4 6 5 4 6 45 45" (number + initial + back-nine scores + total).
    Returns (player_name, list of score values) or None.
    """
    if len(tokens) < 4:
        return None
    # Simulator style: rank 1-4 + letter then scores (e.g. "1 K 4 5 7 ... 45 45")
    if _RANK_RE.match(tokens[0]) and _SINGLE_LETTER_RE.match(tokens[1]):
        name = f"{tokens[0]} {tokens[1]}"
        rest = tokens[2:]
        numbers: List[int] = []
        for t in rest:
            if _INT_RE.match(t):
                numbers.append(int(t))
            else:
                return None  # non-numeric in score area
        if numbers:
            return (name, numbers)
        return None
    return None


def _is_simulator_name_line(tokens: List[str]) -> bool:
    """
    True if line is just 'rank name' with rank 1-4 and a non-numeric
    token after it (e.g. '1 K', '2 B', '1 Kevin').
    """
    return bool(
        len(tokens) == 2
        and _RANK_RE.match(tokens[0])
        and not _INT_RE.match(tokens[1])
        and tokens[1].lower() not in _SCORECARD_SKIP_WORDS
    )


def _collect_following_numeric_lines(
    lines: List[str], start_index: int, max_numbers: int = 11
) -> tuple[List[int], int]:
    """
    From lines[start_index:], consume lines that are only integers (one or more per line).
    Returns (list of numbers, number of lines consumed).
    Use max_numbers=11 for back-nine: 9 scores + optional total(s), so we don't consume the next player's first score.
    """
    numbers: List[int] = []
    i = start_index
    while i < len(lines) and len(numbers) < max_numbers:
        tokens = lines[i].split()
        if not tokens:
            i += 1
            continue
        # Don't consume a line that is just rank 1-4 when we already have 9+ numbers (next player's marker)
        if len(tokens) == 1 and _RANK_RE.match(tokens[0]) and len(numbers) >= 9:
            break
        # Only consume line if every token is numeric
        if not all(_INT_RE.match(t) for t in tokens):
            break
        for t in tokens:
            if len(numbers) >= max_numbers:
                break
            numbers.append(int(t))
        i += 1
    return (numbers, i - start_index)


def _append_simulator_player(
    players: List[DraftPlayerStats],
    hole_scores: List[DraftHoleScore],
    name: str,
    numbers: List[int],
    holes_expected: int,
) -> None:
    """Append one simulator-style player (back nine or full 18) to players and hole_scores."""
    if len(numbers) < 9:
        return
    total_score: int | None = None
    if len(numbers) >= 10 and numbers[-1] == numbers[-2]:
        total_score = numbers[-1]
        numbers = numbers[:-2]
    elif len(numbers) >= 9:
        total_score = numbers[-1]
        numbers = numbers[:-1]
    if len(numbers) == 9:
        players.append(DraftPlayerStats(name=name, total_score=total_score))
        for idx, value in enumerate(numbers, start=10):
            hole_scores.append(DraftHoleScore(player_name=name, hole_number=idx, score=value))
    elif len(numbers) >= holes_expected:
        hole_values = numbers[:holes_expected]
        total_score = numbers[-1] if len(numbers) > holes_expected else total_score or numbers[-1]
        players.append(DraftPlayerStats(name=name, total_score=total_score))
        for idx, value in enumerate(hole_values, start=1):
            hole_scores.append(DraftHoleScore(player_name=name, hole_number=idx, score=value))


def parse_scorecard_text(
    text: str,
    *,
    meta: DraftRoundMeta | None = None,
    holes_expected: int = 18,
) -> DraftRound:
    """
    Parse OCR text from a scorecard-like table into a DraftRound.

    Heuristic assumptions:
    - Each non-header row corresponds to a single player.
    - A row starts with the player name (one or more words) followed by numeric
      tokens representing hole scores and (optionally) a total score.
    - Header rows containing things like "Hole", "Out", or "In" are skipped.
    - Simulator leaderboard lines like "1 K 4 5 7 4 4 6 5 4 6 45 45" are supported
      (digit + letter as name, then 9 scores + total = back nine).
    """
    lines = _non_empty_lines(text)

    players: List[DraftPlayerStats] = []
    hole_scores: List[DraftHoleScore] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        tokens = line.split()

        # Single-token lines: handle before requiring len(tokens) >= 2
        if len(tokens) == 1:
            # Single-token "rank+letter" (e.g. "3R", "1K", "2Y") – rank 1-4 only
            m = _RANK_LETTER_RE.match(tokens[0])
            if m and len(players) < 4:
                name = f"{m.group(1)} {m.group(2)}"
                numbers, consumed = _collect_following_numeric_lines(lines, i + 1)
                i += 1 + consumed
                _append_simulator_player(players, hole_scores, name, numbers, holes_expected)
                continue
            # Consecutive rank (1-4) then letter on two lines: "3" then "R" -> "3 R"
            if _RANK_RE.match(tokens[0]) and i + 1 < len(lines):
                next_tokens = lines[i + 1].strip().split()
                if len(next_tokens) == 1 and _SINGLE_LETTER_RE.match(next_tokens[0]) and len(players) < 4:
                    name = f"{tokens[0]} {next_tokens[0]}"
                    numbers, consumed = _collect_following_numeric_lines(lines, i + 2)
                    i += 2 + consumed
                    _append_simulator_player(players, hole_scores, name, numbers, holes_expected)
                    continue
            i += 1
            continue

        if len(tokens) < 2:
            i += 1
            continue

        # Simulator style: "1 K" on one line (rank 1-4 + letter)
        if _is_simulator_name_line(tokens) and len(players) < 4:
            name = f"{tokens[0]} {tokens[1]}"
            numbers, consumed = _collect_following_numeric_lines(lines, i + 1)
            i += 1 + consumed
            _append_simulator_player(players, hole_scores, name, numbers, holes_expected)
            continue

        if len(tokens) < 3:
            i += 1
            continue

        # Try simulator-style single line: "1 K 4 5 7 4 4 6 5 4 6 45 45"
        if len(players) < 4:
            sim = _parse_simulator_player_line(tokens)
            if sim is not None:
                name, numbers = sim
                _append_simulator_player(players, hole_scores, name, numbers, holes_expected)
                i += 1
                continue

        # Rank (1-4) followed by a longer name on the same line (e.g. "1 Kevin",
        # "2 John Smith"). Treat the whole line as the player name and gather
        # numeric scores from following lines.
        if _RANK_RE.match(tokens[0]) and len(players) < 4:
            # If there are any numeric tokens after the first, this is more likely
            # a scores row ("1 4 5 7 ..."), which is handled elsewhere, so skip.
            has_numeric_after = any(_INT_RE.match(t) for t in tokens[1:])
            has_name_after = any(not _INT_RE.match(t) for t in tokens[1:])
            if has_name_after and not has_numeric_after:
                name = " ".join(tokens)
                numbers, consumed = _collect_following_numeric_lines(lines, i + 1)
                i += 1 + consumed
                _append_simulator_player(players, hole_scores, name, numbers, holes_expected)
                continue

        if _is_header_line(line, tokens):
            i += 1
            continue

        name_parts: list[str] = []
        numeric_tokens: list[str] = []

        # Collect leading name tokens until we encounter something that looks numeric.
        for token in tokens:
            if not name_parts and not _INT_RE.match(token):
                name_parts.append(token)
                continue

            if name_parts and not _INT_RE.match(token):
                if numeric_tokens:
                    numeric_tokens.append(token)
                else:
                    name_parts.append(token)
                continue

            numeric_tokens.append(token)

        if not name_parts or not numeric_tokens:
            i += 1
            continue

        name = " ".join(name_parts)

        numbers = []
        for tok in numeric_tokens:
            if _INT_RE.match(tok):
                try:
                    numbers.append(int(tok))
                except ValueError:
                    continue

        if not numbers:
            i += 1
            continue

        hole_values = numbers[:holes_expected]
        total_score = numbers[-1] if len(numbers) > holes_expected else None

        players.append(DraftPlayerStats(name=name, total_score=total_score))

        for idx, value in enumerate(hole_values, start=1):
            hole_scores.append(
                DraftHoleScore(
                    player_name=name,
                    hole_number=idx,
                    score=value,
                )
            )
        i += 1

    return DraftRound(meta=meta or DraftRoundMeta(), players=players, hole_scores=hole_scores)


def _is_simulator_stats_format(text: str) -> bool:
    """True if text looks like simulator stats (has % or YD and rank+initial)."""
    if "%" not in text and "yd" not in text.lower():
        return False
    lines = _non_empty_lines(text)
    for line in lines:
        tokens = line.strip().split()
        if len(tokens) == 2 and _RANK_RE.match(tokens[0]) and _SINGLE_LETTER_RE.match(tokens[1]):
            return True
        if len(tokens) == 1 and _RANK_LETTER_RE.match(tokens[0]):
            return True
    return False


def _read_simulator_player_marker(lines: List[str], i: int) -> tuple[int | None, int]:
    """
    If lines[i] (and optionally [i+1]) form a rank+initial marker, return (rank 1-4, lines_consumed).
    Otherwise (None, 0).
    """
    if i >= len(lines):
        return (None, 0)
    tokens = lines[i].strip().split()
    if len(tokens) == 2 and _RANK_RE.match(tokens[0]) and _SINGLE_LETTER_RE.match(tokens[1]):
        return (int(tokens[0]), 1)
    if len(tokens) == 1:
        m = _RANK_LETTER_RE.match(tokens[0])
        if m:
            return (int(m.group(1)), 1)
        if _RANK_RE.match(tokens[0]) and i + 1 < len(lines):
            next_tokens = lines[i + 1].strip().split()
            if len(next_tokens) == 1 and _SINGLE_LETTER_RE.match(next_tokens[0]):
                return (int(tokens[0]), 2)
    return (None, 0)


def _collect_tokens_until_marker_or_footer(
    lines: List[str], start_i: int, max_tokens: int = 20
) -> tuple[List[str], int]:
    """Collect tokens from lines[start_i:] until next player marker, footer word, or max_tokens."""
    tokens: List[str] = []
    i = start_i
    while i < len(lines) and len(tokens) < max_tokens:
        line = lines[i]
        parts = line.strip().split()
        if not parts:
            i += 1
            continue
        # Stop at next player marker
        if len(parts) == 2 and _RANK_RE.match(parts[0]) and _SINGLE_LETTER_RE.match(parts[1]):
            break
        if len(parts) == 1 and _RANK_LETTER_RE.match(parts[0]):
            break
        if len(parts) == 1 and _RANK_RE.match(parts[0]) and i + 1 < len(lines):
            next_parts = lines[i + 1].strip().split()
            if len(next_parts) == 1 and _SINGLE_LETTER_RE.match(next_parts[0]):
                break
        # Stop at footer
        if parts[0].lower() in _SIMULATOR_STATS_FOOTER:
            break
        for p in parts:
            tokens.append(p)
            if len(tokens) >= max_tokens:
                break
        i += 1
    return (tokens, i - start_i)


def _apply_simulator_stats_to_player(player: DraftPlayerStats, tokens: List[str]) -> None:
    """
    Parse simulator stats tokens: percentages (fairways, GIR, scramble, sand), YD, putts, out/total.
    Store percentages as hit/possible with denominator 100.
    """
    percentages: List[int] = []
    drive_yd: int | None = None
    integers: List[int] = []
    for t in tokens:
        m = _PCT_RE.match(t)
        if m:
            percentages.append(int(m.group(1)))
            continue
        m = _YD_RE.match(t)
        if m:
            drive_yd = int(m.group(1))
            continue
        if t.strip() in ("-", "–", "—"):
            percentages.append(-1)  # placeholder for N/A
            continue
        if _INT_RE.match(t):
            integers.append(int(t))
    if drive_yd is not None and player.avg_drive_distance is None:
        player.avg_drive_distance = float(drive_yd)
    if len(percentages) >= 1 and percentages[0] >= 0 and player.fairways_hit is None:
        player.fairways_hit = percentages[0]
        player.fairways_possible = 100
    if len(percentages) >= 2 and percentages[1] >= 0 and player.gir is None:
        player.gir = percentages[1]
        player.gir_possible = 100
    if len(percentages) >= 3 and percentages[2] >= 0 and player.scramble_successes is None:
        player.scramble_successes = percentages[2]
        player.scramble_opportunities = 100
    if len(percentages) >= 4 and percentages[3] >= 0 and player.sand_save_successes is None:
        player.sand_save_successes = percentages[3]
        player.sand_save_opportunities = 100
    if len(integers) >= 1 and player.total_putts is None:
        player.total_putts = integers[0]
    if len(integers) >= 2 and player.total_score is None:
        player.total_score = integers[-1]


def parse_stats_text(
    text: str,
    *,
    existing_round: DraftRound | None = None,
) -> DraftRound:
    """
    Parse OCR text from a per-player stats sheet into a DraftRound.

    When text looks like simulator stats (% and/or YD, rank+initial lines), merges
    stats into existing_round by position (rank 1 -> players[0], etc.). Otherwise
    uses heuristic: name at line start, ratios and integers, matched by name.
    """
    round_obj = existing_round or DraftRound()

    # Simulator stats: match by position (rank 1-4 -> players[0..3])
    if existing_round and _is_simulator_stats_format(text):
        lines = _non_empty_lines(text)
        i = 0
        while i < len(lines):
            rank, marker_consumed = _read_simulator_player_marker(lines, i)
            if rank is not None:
                i += marker_consumed
                stats_tokens, tok_consumed = _collect_tokens_until_marker_or_footer(
                    lines, i, max_tokens=20
                )
                i += tok_consumed
                idx = rank - 1
                if 0 <= idx < len(existing_round.players):
                    _apply_simulator_stats_to_player(existing_round.players[idx], stats_tokens)
            else:
                i += 1
        return round_obj

    players_by_key = {p.name.lower(): p for p in round_obj.players}

    def _find_player_for_stats(stats_name: str) -> DraftPlayerStats | None:
        key = stats_name.lower()
        if key in players_by_key:
            return players_by_key[key]
        # Simulator: stats screen may show only initial "K" but scorecard has "1 K"
        if len(key) == 1 and key.isalpha():
            for p in round_obj.players:
                if p.name.lower().endswith(" " + key) or p.name.lower() == key:
                    return p
        # Match last word of multi-word name (e.g. "K" matches "1 K")
        for p in round_obj.players:
            parts = p.name.lower().split()
            if parts and parts[-1] == key:
                return p
        return None

    lines = _non_empty_lines(text)
    for line in lines:
        tokens = line.split()
        if len(tokens) < 2:
            continue

        name_parts: list[str] = []
        rest_tokens: list[str] = []

        # Heuristic: name comes first until we see something clearly numeric/ratio-like.
        for token in tokens:
            if not name_parts and not _INT_RE.match(token) and not _RATIO_RE.match(token):
                name_parts.append(token)
                continue

            if name_parts and not rest_tokens and not _INT_RE.match(token) and not _RATIO_RE.match(token):
                # Still consuming a multi-word name.
                name_parts.append(token)
                continue

            rest_tokens.append(token)

        if not name_parts or not rest_tokens:
            continue

        name = " ".join(name_parts)
        player = _find_player_for_stats(name)
        if player is None:
            player = DraftPlayerStats(name=name)
            round_obj.players.append(player)
            players_by_key[name.lower()] = player

        ratios: list[tuple[int, int]] = []
        singles: list[int] = []

        for token in rest_tokens:
            m = _RATIO_RE.match(token)
            if m:
                ratios.append((int(m.group(1)), int(m.group(2))))
                continue

            if _INT_RE.match(token):
                try:
                    singles.append(int(token))
                except ValueError:
                    continue

        # Map ratios to fairways, GIR, scramble, sand saves in order, if absent.
        if ratios:
            if player.fairways_hit is None and player.fairways_possible is None:
                h, p = ratios[0]
                player.fairways_hit = h
                player.fairways_possible = p

            if len(ratios) > 1 and player.gir is None and player.gir_possible is None:
                h, p = ratios[1]
                player.gir = h
                player.gir_possible = p

            if len(ratios) > 2 and player.scramble_successes is None and player.scramble_opportunities is None:
                h, p = ratios[2]
                player.scramble_successes = h
                player.scramble_opportunities = p

            if len(ratios) > 3 and player.sand_save_successes is None and player.sand_save_opportunities is None:
                h, p = ratios[3]
                player.sand_save_successes = h
                player.sand_save_opportunities = p

        # Map standalone integers to avg drive distance and total putts if those are missing.
        if singles:
            if player.avg_drive_distance is None:
                player.avg_drive_distance = float(singles[0])

            if len(singles) > 1 and player.total_putts is None:
                player.total_putts = singles[1]

    return round_obj

