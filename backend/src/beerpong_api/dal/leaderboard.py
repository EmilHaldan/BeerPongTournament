"""DAL function for computing the leaderboard.

Ties are counted as **neither** a win nor a loss.
"""

from __future__ import annotations

from collections import defaultdict

from beerpong_api.dal.matches import list_matches
from beerpong_api.db.models import LeaderboardEntry


def compute_leaderboard() -> list[LeaderboardEntry]:
    """Build the leaderboard from all stored matches.

    Aggregation rules per team:
    - ``total_score`` = sum of that team's score across all matches
    - ``total_wins``  = matches where team scored higher than opponent
    - ``total_loss``  = matches where team scored lower than opponent
    - Ties (equal scores) count as neither win nor loss.

    Sorted by ``total_wins`` descending, then ``total_score`` descending.
    """
    stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total_score": 0, "total_wins": 0, "total_loss": 0},
    )

    for match in list_matches():
        # Team 1
        stats[match.team1_name]["total_score"] += match.team1_score
        # Team 2
        stats[match.team2_name]["total_score"] += match.team2_score

        if match.team1_score > match.team2_score:
            stats[match.team1_name]["total_wins"] += 1
            stats[match.team2_name]["total_loss"] += 1
        elif match.team2_score > match.team1_score:
            stats[match.team2_name]["total_wins"] += 1
            stats[match.team1_name]["total_loss"] += 1
        # Ties: no change to wins/losses

    entries = [
        LeaderboardEntry(team_name=team, **s) for team, s in stats.items()
    ]
    entries.sort(key=lambda e: (e.total_wins, e.total_score), reverse=True)
    return entries
