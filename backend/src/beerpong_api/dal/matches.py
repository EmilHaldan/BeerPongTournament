"""DAL functions for match results."""

from __future__ import annotations

from beerpong_api.db.client import get_container
from beerpong_api.db.models import MatchCreate, MatchResult


def _normalize_team_name(name: str) -> str:
    """Normalize a team name: strip whitespace and title-case."""
    return name.strip().title()


def insert_match(payload: MatchCreate) -> MatchResult:
    """Validate, normalise and persist a new match result.

    The ``phase`` field on the persisted document is server-authoritative —
    stamped from the current ``HeatState.phase`` and any client-supplied
    value is ignored. When the current phase is ``semifinals`` or
    ``finals``, tied scores are rejected via ``ValueError``.

    When a finals match is persisted, the tournament is auto-frozen and
    the phase advances to ``complete``.

    Returns the saved ``MatchResult``.
    """
    # Local imports to avoid a circular dependency: dal.heat imports
    # dal.matches.list_matches.
    from beerpong_api.dal.heat import (
        _get_heat_state,  # pyright: ignore[reportPrivateUsage]
        _save_heat_state,  # pyright: ignore[reportPrivateUsage]
    )

    state = _get_heat_state()
    phase = state.phase

    if phase in {"semifinals", "finals"} and payload.team1_score == payload.team2_score:
        raise ValueError(
            "Knockout matches cannot end in a tie — play sudden death until someone scores."
        )

    match = MatchResult(
        team1_name=_normalize_team_name(payload.team1_name),
        team2_name=_normalize_team_name(payload.team2_name),
        team1_score=payload.team1_score,
        team2_score=payload.team2_score,
        heat=payload.heat,
        phase=phase,
    )

    container = get_container()
    doc = match.model_dump(by_alias=True)
    container.upsert_item(doc)

    # Auto-freeze on finals submission. Finals has exactly one matchup;
    # a non-tied scored match means the champion is known.
    # NOTE: re-read state so we pick up any concurrent mutation and avoid
    # overwriting frozen back to False when we save the phase change.
    if phase == "finals":
        fresh = _get_heat_state()
        fresh.frozen = True
        fresh.phase = "complete"
        _save_heat_state(fresh)

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
