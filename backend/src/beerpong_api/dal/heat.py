"""DAL functions for heat management.

Handles tracking the current heat number and generating matchups.
Phase 1 (cycle 1): round-robin via circle method so every team plays every other.
Phase 2+ (cycle 2+): score-seeded round-robin for competitive matchmaking.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from beerpong_api.dal.leaderboard import compute_leaderboard
from beerpong_api.dal.matches import list_matches
from beerpong_api.dal.teams import get_active_team_names
from beerpong_api.db.client import get_state_container
from beerpong_api.db.models import HeatInfo, HeatMatchup, HeatState, LeaderboardEntry

# Heat timer duration in seconds (10 minutes)
HEAT_TIMER_SECONDS = 600


def _get_heat_state() -> HeatState:
    """Load the current heat state from the DB, or return defaults."""
    container = get_state_container()
    items = container.query_items(
        query="SELECT * FROM c WHERE c.tournamentId = 'default'",
        enable_cross_partition_query=False,
    )
    for item in items:  # pyright: ignore[reportUnknownVariableType, reportGeneralTypeIssues]
        if item.get("id") == "heat_state":  # pyright: ignore[reportUnknownMemberType]
            return HeatState(**item)  # pyright: ignore[reportUnknownArgumentType]
    return HeatState()


def _save_heat_state(state: HeatState) -> None:
    """Persist the heat state document."""
    container = get_state_container()
    doc = state.model_dump(by_alias=True)
    container.upsert_item(doc)


def get_current_heat() -> int:
    """Return the current heat number."""
    return _get_heat_state().current_heat


_BYE = "__BYE__"


def _circle_method_round(teams: list[str], round_index: int) -> list[tuple[str, str]]:
    """Generate pairings for one round using the circle (polygon) method.

    Fix teams[0] in place, rotate the rest by round_index positions,
    then pair outside-in.  Returns pairs as (team_a, team_b) tuples.
    """
    n = len(teams)
    if n < 2:
        return []

    fixed = teams[0]
    rotating = teams[1:]
    # Rotate left by round_index positions
    r = round_index % len(rotating)
    rotated = rotating[r:] + rotating[:r]

    ordered = [fixed] + rotated
    pairs: list[tuple[str, str]] = []
    for i in range(n // 2):
        pairs.append((ordered[i], ordered[n - 1 - i]))
    return pairs


def _compute_round_robin_state(
    team_names: list[str],
) -> tuple[int, set[tuple[str, str]], set[tuple[str, str]]]:
    """Derive the current round-robin cycle and which pairs have been played.

    Returns (cycle_number, pairs_played_this_cycle, all_possible_pairs).
    Cycle is 1-indexed.  A cycle is complete when every possible pair has
    played at least ``cycle`` times.
    """
    matches = list_matches()
    all_possible: set[tuple[str, str]] = set()
    for i, t1 in enumerate(team_names):
        for t2 in team_names[i + 1 :]:
            all_possible.add(tuple(sorted([t1, t2])))  # pyright: ignore[reportArgumentType]

    if not all_possible:
        return (1, set(), all_possible)

    pair_counts: dict[tuple[str, str], int] = defaultdict(int)
    for m in matches:
        pair: tuple[str, str] = tuple(sorted([m.team1_name, m.team2_name]))  # pyright: ignore[reportAssignmentType]
        if pair in all_possible:
            pair_counts[pair] += 1

    min_count = min((pair_counts.get(p, 0) for p in all_possible), default=0)
    cycle = min_count + 1

    played_this_cycle = {p for p in all_possible if pair_counts.get(p, 0) >= cycle}
    return (cycle, played_this_cycle, all_possible)


def generate_matchups(last_heat: bool = False) -> tuple[list[HeatMatchup], list[str]]:
    """Generate matchups for the next round and a sit-out list.

    Two scheduling paths are supported:

    * Round-robin (default): circle method with cycle detection. Used when
      the tables count permits every team to play and ``last_heat`` is False.
      Cycle 1 uses alphabetical seeding; cycle 2+ uses standings-seeded
      ordering for competitive matchmaking.
    * Games-balance: triggered when EITHER the table count cannot fit all
      teams (``tables * 2 < teams_count``) OR the caller passes
      ``last_heat=True``. Teams are sorted ascending by
      ``(total_matches, total_score)`` so those with the fewest games (or
      lowest scores as the tiebreaker) get priority to play. The remaining
      tail sits this heat out.

    Returns a tuple ``(matchups, sitting_out)`` where ``sitting_out`` is the
    list of team names that should not play this heat (sorted alphabetically).
    """
    leaderboard = compute_leaderboard()
    all_team_names = sorted(get_active_team_names())
    n = len(all_team_names)

    if n < 2:
        return ([], [])

    # Build score map for point display
    score_map: dict[str, int] = {}
    for entry in leaderboard:
        score_map[entry.team_name] = entry.total_score
    for name in all_team_names:
        if name not in score_map:
            score_map[name] = 0

    tables = _get_heat_state().tables
    constrained = tables * 2 < n
    # An odd team count means one team must sit out every heat. Round-robin's
    # BYE padding silently drops a team without reporting it, so route odd
    # counts through the balance path which tracks the sitter explicitly.
    odd = n % 2 == 1

    if constrained or last_heat or odd:
        return _generate_balance_matchups(all_team_names, leaderboard, score_map, tables)

    return (_generate_round_robin_matchups(all_team_names, leaderboard, score_map), [])


def _generate_round_robin_matchups(
    all_team_names: list[str],
    leaderboard: list[LeaderboardEntry],
    score_map: dict[str, int],
) -> list[HeatMatchup]:
    """Pure round-robin pairings via the circle method, with cycle detection."""
    cycle, played_this_cycle, all_possible = _compute_round_robin_state(all_team_names)
    remaining = all_possible - played_this_cycle

    if not remaining:
        # All pairs played this cycle — start a fresh cycle
        cycle += 1
        played_this_cycle = set()
        remaining = all_possible

    # Choose team ordering based on cycle
    if cycle == 1:
        teams = list(all_team_names)
    else:
        win_map: dict[str, tuple[int, int]] = {}
        for entry in leaderboard:
            win_map[entry.team_name] = (entry.total_wins, entry.total_score)
        teams = sorted(
            all_team_names,
            key=lambda t: win_map.get(t, (0, 0)),
            reverse=True,
        )

    # Pad for odd count
    padded = list(teams)
    if len(padded) % 2 == 1:
        padded.append(_BYE)

    n_rounds = len(padded) - 1

    # Try each circle-method round to find one whose pairs are all unplayed
    for round_offset in range(n_rounds):
        pairs = _circle_method_round(padded, round_offset)
        real_pairs = [(a, b) for a, b in pairs if a != _BYE and b != _BYE]
        pair_keys = {tuple(sorted([a, b])) for a, b in real_pairs}  # pyright: ignore[reportArgumentType]
        if pair_keys and pair_keys.issubset(remaining):
            return _pairs_to_matchups(real_pairs, score_map)

    # Fallback: greedily pick unplayed pairs
    return _greedy_matchups(all_team_names, remaining, score_map)


def _generate_balance_matchups(
    all_team_names: list[str],
    leaderboard: list[LeaderboardEntry],
    score_map: dict[str, int],
    tables: int,
) -> tuple[list[HeatMatchup], list[str]]:
    """Pick a subset of teams by lowest (total_matches, total_score) and pair them.

    The selected subset (those that play) is fed to the circle method in
    standings-sorted order so the pairings still mix high- and low-ranked
    teams visually. Anyone left over sits out.
    """
    n = len(all_team_names)
    games_this_heat = min(tables, n // 2)
    playing_count = 2 * games_this_heat

    # (total_matches, total_score) lookup – missing entries default to (0, 0)
    stats: dict[str, tuple[int, int]] = {
        e.team_name: (e.total_matches, e.total_score) for e in leaderboard
    }
    for name in all_team_names:
        stats.setdefault(name, (0, 0))

    # Ascending: fewest matches first, lowest score as tiebreaker.
    # Alphabetical name as the final stable tiebreaker for deterministic output.
    sorted_by_priority = sorted(
        all_team_names,
        key=lambda t: (stats[t][0], stats[t][1], t),
    )

    playing = sorted_by_priority[:playing_count]
    sitting = sorted(sorted_by_priority[playing_count:])

    # Use the standings-sorted order (priority order) within the selected
    # subset as input to the circle method – preserves the "mix" intent.
    matchups = _circle_method_pairings(playing, score_map)
    return (matchups, sitting)


def _circle_method_pairings(
    teams: list[str], score_map: dict[str, int]
) -> list[HeatMatchup]:
    """Run a single circle-method round on the given (already-ordered) teams.

    Pads with a BYE for odd counts so callers don't need to special-case.
    Returns the resulting matchups, dropping any pair that involved the BYE.
    """
    if len(teams) < 2:
        return []
    padded = list(teams)
    if len(padded) % 2 == 1:
        padded.append(_BYE)
    pairs = _circle_method_round(padded, 0)
    real_pairs = [(a, b) for a, b in pairs if a != _BYE and b != _BYE]
    return _pairs_to_matchups(real_pairs, score_map)


def _pairs_to_matchups(
    pairs: list[tuple[str, str]], score_map: dict[str, int]
) -> list[HeatMatchup]:
    """Convert a list of (team1, team2) pairs into HeatMatchup objects."""
    return [
        HeatMatchup(
            team1_name=t1,
            team2_name=t2,
            team1_points=score_map.get(t1, 0),
            team2_points=score_map.get(t2, 0),
        )
        for t1, t2 in pairs
    ]


def _greedy_matchups(
    team_names: list[str],
    remaining: set[tuple[str, str]],
    score_map: dict[str, int],
) -> list[HeatMatchup]:
    """Greedily pair teams from unplayed pairs when no clean round exists."""
    used: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for pair in sorted(remaining):
        t1, t2 = pair
        if t1 not in used and t2 not in used:
            pairs.append((t1, t2))
            used.update([t1, t2])
    return _pairs_to_matchups(pairs, score_map)


def _get_heat_matches(heat_number: int) -> dict[tuple[str, str], tuple[int, int]]:
    """Return a dict mapping (team1, team2) -> (score1, score2) for the given heat.

    Keys are ordered so the lower-alpha team is first, to allow matching
    regardless of which side each team was on when the match was recorded.
    """
    matches = list_matches()
    result: dict[tuple[str, str], tuple[int, int]] = {}
    for m in matches:
        if m.heat != heat_number:
            continue
        key = tuple(sorted([m.team1_name, m.team2_name]))
        # Store scores in the order matching the sorted key
        if m.team1_name <= m.team2_name:
            result[key] = (m.team1_score, m.team2_score)  # pyright: ignore[reportArgumentType]
        else:
            result[key] = (m.team2_score, m.team1_score)  # pyright: ignore[reportArgumentType]
    return result


def get_heat_info() -> HeatInfo:
    """Return the current heat number, matchups with recorded status, and team lists.

    Recorded matches for the heat always take priority. If stored matchup
    pairings have gone stale (e.g. heat was set back after results changed
    the standings), recorded matches are still shown correctly without
    duplicating teams.
    """
    state = _get_heat_state()
    current = state.current_heat
    heat_matches = _get_heat_matches(current)

    # Build current score lookup for point display
    leaderboard = compute_leaderboard()
    score_map: dict[str, int] = {e.team_name: e.total_score for e in leaderboard}

    # Precompute which teams appear in any recorded match for fast lookup
    teams_in_recorded: set[str] = set()
    for key in heat_matches:
        teams_in_recorded.update(key)

    teams_recorded: list[str] = []
    teams_not_recorded: list[str] = []
    enriched: list[HeatMatchup] = []
    handled_teams: set[str] = set()

    # --- Use stored matchups or generate new ones ---
    if state.stored_matchups:
        base_matchups = state.stored_matchups
        stored_sitting_out = list(state.sitting_out)
    else:
        base_matchups, stored_sitting_out = generate_matchups()
        state.stored_matchups = base_matchups
        state.sitting_out = stored_sitting_out
        _save_heat_state(state)

    # --- Pass 1: process stored matchups in order (preserving table numbers) ---
    for mu in base_matchups:
        if mu.team1_name in handled_teams or mu.team2_name in handled_teams:
            continue

        key: tuple[str, str] = tuple(sorted([mu.team1_name, mu.team2_name]))  # pyright: ignore[reportAssignmentType]

        if key in heat_matches:
            # Stored matchup directly matches a recorded match
            handled_teams.update([mu.team1_name, mu.team2_name])
            if mu.team1_name <= mu.team2_name:
                s1, s2 = heat_matches[key]
            else:
                s2, s1 = heat_matches[key]

            winner = None
            if s1 > s2:
                winner = mu.team1_name
            elif s2 > s1:
                winner = mu.team2_name

            enriched.append(
                HeatMatchup(
                    team1_name=mu.team1_name,
                    team2_name=mu.team2_name,
                    team1_points=score_map.get(mu.team1_name, 0),
                    team2_points=score_map.get(mu.team2_name, 0),
                    team1_score=s1,
                    team2_score=s2,
                    recorded=True,
                    winner=winner,
                )
            )
            teams_recorded.extend([mu.team1_name, mu.team2_name])
        else:
            # If either team already played a different opponent, skip this
            # stale matchup — the actual recorded match is added in pass 2.
            if mu.team1_name in teams_in_recorded or mu.team2_name in teams_in_recorded:
                continue
            # Neither team has played yet — pending matchup
            handled_teams.update([mu.team1_name, mu.team2_name])
            enriched.append(
                HeatMatchup(
                    team1_name=mu.team1_name,
                    team2_name=mu.team2_name,
                    team1_points=score_map.get(mu.team1_name, 0),
                    team2_points=score_map.get(mu.team2_name, 0),
                    team1_score=None,
                    team2_score=None,
                    recorded=False,
                    winner=None,
                )
            )
            teams_not_recorded.extend([mu.team1_name, mu.team2_name])

    # --- Pass 2: add recorded matches not covered by stored matchups ---
    for key, (s1, s2) in heat_matches.items():
        t1, t2 = key  # alphabetically sorted
        if t1 in handled_teams and t2 in handled_teams:
            continue
        handled_teams.update([t1, t2])

        winner = None
        if s1 > s2:
            winner = t1
        elif s2 > s1:
            winner = t2

        enriched.append(
            HeatMatchup(
                team1_name=t1,
                team2_name=t2,
                team1_points=score_map.get(t1, 0),
                team2_points=score_map.get(t2, 0),
                team1_score=s1,
                team2_score=s2,
                recorded=True,
                winner=winner,
            )
        )
        teams_recorded.extend([t1, t2])

    # Teams that are listed as sitting out but actually have a recorded match
    # for this heat should drop off the display — recorded matches win.
    teams_sitting_out = sorted(t for t in stored_sitting_out if t not in teams_in_recorded)

    return HeatInfo(
        current_heat=current,
        matchups=enriched,
        teams_recorded=sorted(teams_recorded),
        teams_not_recorded=sorted(teams_not_recorded),
        teams_sitting_out=teams_sitting_out,
        timer_duration=state.timer_duration,
        timer_started_at=state.heat_timer_started_at,
        tables=state.tables,
        frozen=state.frozen,
    )


def advance_heat(last_heat: bool = False) -> HeatInfo:
    """Increment the heat counter and return the new heat info.

    Passing ``last_heat=True`` forces the games-balance scheduler path so
    teams with the fewest matches get priority even when tables would
    otherwise permit a full round-robin slate.
    """
    state = _get_heat_state()
    state.current_heat += 1
    matchups, sitting = generate_matchups(last_heat=last_heat)
    state.stored_matchups = matchups
    state.sitting_out = sitting
    state.heat_timer_started_at = None
    _save_heat_state(state)
    return get_heat_info()


def set_heat(heat_number: int) -> HeatInfo:
    """Set the heat counter to an explicit value and return the new heat info."""
    state = _get_heat_state()
    state.current_heat = heat_number
    matchups, sitting = generate_matchups()
    state.stored_matchups = matchups
    state.sitting_out = sitting
    state.heat_timer_started_at = None
    _save_heat_state(state)
    return get_heat_info()


def start_heat_timer() -> HeatInfo:
    """Record a timer start 6 seconds in the future (for 5-count countdown) and return heat info."""
    state = _get_heat_state()
    state.heat_timer_started_at = (datetime.now(UTC) + timedelta(seconds=6)).isoformat()
    _save_heat_state(state)
    return get_heat_info()


def set_timer_duration(seconds: int) -> HeatInfo:
    """Update the heat timer duration and return heat info."""
    state = _get_heat_state()
    state.timer_duration = seconds
    _save_heat_state(state)
    return get_heat_info()


def set_tables(count: int) -> HeatInfo:
    """Update the tables count (number of physical tables) and return heat info."""
    state = _get_heat_state()
    state.tables = count
    _save_heat_state(state)
    return get_heat_info()


def set_frozen(frozen: bool) -> HeatInfo:
    """Freeze or unfreeze the tournament. While frozen, POST /matches is rejected."""
    state = _get_heat_state()
    state.frozen = frozen
    _save_heat_state(state)
    return get_heat_info()


def is_frozen() -> bool:
    """Return True if the tournament is currently frozen."""
    return _get_heat_state().frozen
