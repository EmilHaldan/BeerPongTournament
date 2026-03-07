"""DAL functions for heat management.

Handles tracking the current heat number and generating matchups
based on team standings (total score acts as ELO).
"""

from __future__ import annotations

from datetime import UTC, datetime

from beerpong_api.dal.leaderboard import compute_leaderboard
from beerpong_api.dal.matches import list_matches
from beerpong_api.dal.teams import get_team_names
from beerpong_api.db.client import get_state_container
from beerpong_api.db.models import HeatInfo, HeatMatchup, HeatState
from beerpong_api.settings import get_settings


def _get_heat_state() -> HeatState:
    """Load the current heat state from the DB, or return defaults."""
    container = get_state_container()
    items = container.query_items(
        query="SELECT * FROM c WHERE c.tournamentId = 'default'",
        enable_cross_partition_query=False,
    )
    for item in items:  # pyright: ignore[reportUnknownVariableType]
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


def generate_matchups() -> list[HeatMatchup]:
    """Generate matchups for the next round.

    Teams are sorted by total score (descending) and paired adjacently:
    1st vs 2nd, 3rd vs 4th, etc.  If there is an odd number of teams,
    the last team gets no matchup (a bye).
    """
    leaderboard = compute_leaderboard()
    all_team_names = get_team_names()

    # Build a mapping of team -> total_score from leaderboard
    score_map: dict[str, int] = {}
    for entry in leaderboard:
        score_map[entry.team_name] = entry.total_score

    # Include teams that have no matches yet (score = 0)
    for name in all_team_names:
        if name not in score_map:
            score_map[name] = 0

    # Sort by total_score descending, then alphabetically for tiebreaker
    sorted_teams = sorted(
        score_map.items(),
        key=lambda x: (-x[1], x[0]),
    )

    matchups: list[HeatMatchup] = []
    for i in range(0, len(sorted_teams) - 1, 2):
        t1_name, t1_pts = sorted_teams[i]
        t2_name, t2_pts = sorted_teams[i + 1]
        matchups.append(
            HeatMatchup(
                team1_name=t1_name,
                team2_name=t2_name,
                team1_points=t1_pts,
                team2_points=t2_pts,
            )
        )

    return matchups


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
    else:
        base_matchups = generate_matchups()
        state.stored_matchups = base_matchups
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
                    team1_points=mu.team1_points,
                    team2_points=mu.team2_points,
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
            enriched.append(mu)
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

    return HeatInfo(
        current_heat=current,
        matchups=enriched,
        teams_recorded=sorted(teams_recorded),
        teams_not_recorded=sorted(teams_not_recorded),
        timer_duration=get_settings().HEAT_TIMER,
        timer_started_at=state.heat_timer_started_at,
    )


def advance_heat() -> HeatInfo:
    """Increment the heat counter and return the new heat info."""
    state = _get_heat_state()
    state.current_heat += 1
    state.stored_matchups = generate_matchups()
    state.heat_timer_started_at = None
    _save_heat_state(state)
    return get_heat_info()


def set_heat(heat_number: int) -> HeatInfo:
    """Set the heat counter to an explicit value and return the new heat info."""
    state = _get_heat_state()
    state.current_heat = heat_number
    state.stored_matchups = generate_matchups()
    state.heat_timer_started_at = None
    _save_heat_state(state)
    return get_heat_info()


def start_heat_timer() -> HeatInfo:
    """Record a timer start 6 seconds in the future (for 5-count countdown) and return heat info."""
    from datetime import timedelta

    state = _get_heat_state()
    state.heat_timer_started_at = (datetime.now(UTC) + timedelta(seconds=6)).isoformat()
    _save_heat_state(state)
    return get_heat_info()
