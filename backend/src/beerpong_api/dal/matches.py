"""DAL functions for match results."""

from __future__ import annotations

from beerpong_api.db.client import get_container
from beerpong_api.db.models import MatchCreate, MatchResult


def _normalize_team_name(name: str) -> str:
    """Normalize a team name: strip whitespace and title-case."""
    return name.strip().title()


def insert_match(payload: MatchCreate) -> MatchResult:
    """Validate, normalise and persist a new match result.

    Returns the saved ``MatchResult``.
    """
    match = MatchResult(
        team1_name=_normalize_team_name(payload.team1_name),
        team2_name=_normalize_team_name(payload.team2_name),
        team1_score=payload.team1_score,
        team2_score=payload.team2_score,
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
    return [MatchResult(**item) for item in items]  # pyright: ignore[reportUnknownArgumentType]


def delete_match(match_id: str) -> bool:
    """Delete a single match by its ID.

    Returns True if the item was deleted, False if it was not found.
    """
    from azure.cosmos.exceptions import CosmosResourceNotFoundError  # pyright: ignore[reportMissingImports]

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
    items = list(container.query_items(query=query, enable_cross_partition_query=False))  # pyright: ignore[reportUnknownArgumentType]
    for item in items:
        container.delete_item(item=item["id"], partition_key="default")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return len(items)
