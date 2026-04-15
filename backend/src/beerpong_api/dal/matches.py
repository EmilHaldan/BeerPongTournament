"""DAL functions for match results."""

from __future__ import annotations

from beerpong_api.db.client import get_container
from beerpong_api.db.models import MatchCreate, MatchResult


class DuplicateMatchError(Exception):
    """Raised when a match for the same team pair + heat already exists."""


_DUPLICATE_MATCH_MESSAGE = "Match has already been submitted, talk to Emil or Sophia to reset it"


def _normalize_team_name(name: str) -> str:
    """Normalize a team name: strip whitespace and title-case."""
    return name.strip().title()


def _match_exists_for_heat(team1: str, team2: str, heat: int) -> bool:
    """Return True if a match already exists for the unordered team pair at ``heat``."""
    container = get_container()
    query = (
        "SELECT c.team1_name, c.team2_name FROM c "
        "WHERE c.tournamentId = 'default' AND c.heat = @heat"
    )
    parameters: list[dict[str, object]] = [{"name": "@heat", "value": heat}]
    items = container.query_items(
        query=query,
        parameters=parameters,
        enable_cross_partition_query=False,
    )
    target = frozenset({team1, team2})
    for item in items:  # pyright: ignore[reportUnknownVariableType, reportGeneralTypeIssues]
        existing = frozenset(
            {
                item.get("team1_name"),  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                item.get("team2_name"),  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            }
        )
        if existing == target:
            return True
    return False


def insert_match(payload: MatchCreate) -> MatchResult:
    """Validate, normalise and persist a new match result.

    Returns the saved ``MatchResult``. Raises ``DuplicateMatchError`` if a
    match for the same unordered team pair already exists at the same heat.
    """
    team1 = _normalize_team_name(payload.team1_name)
    team2 = _normalize_team_name(payload.team2_name)

    if _match_exists_for_heat(team1, team2, payload.heat):
        raise DuplicateMatchError(_DUPLICATE_MATCH_MESSAGE)

    match = MatchResult(
        team1_name=team1,
        team2_name=team2,
        team1_score=payload.team1_score,
        team2_score=payload.team2_score,
        heat=payload.heat,
    )

    container = get_container()
    doc = match.model_dump(by_alias=True)
    container.upsert_item(doc)
    return match


def list_matches() -> list[MatchResult]:
    """Return all match results."""
    container = get_container()
    query = "SELECT * FROM c WHERE c.tournamentId = 'default' ORDER BY c.created_at DESC"
    items = container.query_items(query=query, enable_cross_partition_query=False)
    return [MatchResult(**item) for item in items]  # pyright: ignore[reportUnknownArgumentType, reportGeneralTypeIssues]


def delete_match(match_id: str) -> bool:
    """Delete a single match by its ID.

    Returns True if the item was deleted, False if it was not found.
    """
    from azure.cosmos.exceptions import (
        CosmosResourceNotFoundError,  # pyright: ignore[reportMissingImports]
    )

    container = get_container()
    try:
        container.delete_item(item=match_id, partition_key="default")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        return True
    except CosmosResourceNotFoundError:
        return False


def reset_matches() -> int:
    """Delete every match in the default tournament.

    Returns the number of deleted documents.
    """
    container = get_container()
    query = "SELECT c.id FROM c WHERE c.tournamentId = 'default'"
    items = list(container.query_items(query=query, enable_cross_partition_query=False))  # pyright: ignore[reportUnknownArgumentType, reportArgumentType]
    for item in items:
        container.delete_item(item=item["id"], partition_key="default")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return len(items)
